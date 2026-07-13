"""
Node: Extract Criteria

Step 3 of the QA process - extract eligibility criteria and map to screener fields.
"""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    EligibilityCriterion,
    FieldMapping,
    ImpactLevel,
    ResearchState,
)
from ..tools.screener_fields import format_fields_for_prompt
from ..tools.vision_helper import is_pdf_vision_content


def extract_json_payload(response_text: str) -> str:
    """Best-effort extraction of a JSON object from an LLM response.

    Handles ```json fences, bare ``` fences, and prose wrapped around the JSON by
    falling back to the outermost { ... } span.
    """
    text = (response_text or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return text


def parse_field_mapping(response_text: str, program_name: str) -> FieldMapping:
    """Parse the extraction LLM response into a FieldMapping.

    Raises json.JSONDecodeError / ValueError / TypeError on unusable responses so
    the caller can retry or fail loudly instead of returning an empty mapping.
    """
    data = json.loads(extract_json_payload(response_text))
    if not isinstance(data, dict):
        raise ValueError("Extraction response was not a JSON object")

    # Map lower-cased value -> enum so case variants ("high", "HIGH") resolve
    # correctly (the model emits lowercase; enum values are title-case).
    impact_by_value = {level.value.lower(): level for level in ImpactLevel}

    def parse_impact(value) -> ImpactLevel:
        normalized = value.strip().lower() if isinstance(value, str) else None
        return impact_by_value.get(normalized, ImpactLevel.MEDIUM)

    def build(items, is_gap: bool) -> list[EligibilityCriterion]:
        return [
            EligibilityCriterion(
                criterion=item.get("criterion", ""),
                source_reference=item.get("source_reference", ""),
                source_url=item.get("source_url"),
                # Data gaps have no screener field / evaluation logic by definition.
                screener_fields=None if is_gap else item.get("screener_fields"),
                evaluation_logic=None if is_gap else item.get("evaluation_logic"),
                notes=item.get("notes", ""),
                impact=parse_impact(item.get("impact")),
            )
            for item in (items or [])
            if isinstance(item, dict)
        ]

    return FieldMapping(
        program_name=program_name,
        criteria_can_evaluate=build(data.get("criteria_can_evaluate"), False),
        criteria_cannot_evaluate=build(data.get("criteria_cannot_evaluate"), True),
        summary=data.get("summary", ""),
        recommendations=data.get("recommendations", []),
    )


def _save_raw_response(output_dir: str | None, raw_response: str) -> str | None:
    """Persist an unparseable extraction response for debugging; return a note."""
    if not output_dir or not raw_response:
        return None
    try:
        from pathlib import Path

        path = Path(output_dir) / "extract_criteria_raw_response.txt"
        path.write_text(raw_response, encoding="utf-8")
        return f"Raw extraction response saved to {path.name} for debugging"
    except Exception:
        return None


async def extract_criteria_node(state: ResearchState) -> dict:
    """
    Extract eligibility criteria from documentation and map to screener fields.

    This node:
    1. Reviews all source documentation
    2. Extracts eligibility criteria with citations
    3. Maps each criterion to available screener fields
    4. Identifies data gaps
    """
    messages = list(state.messages)
    messages.append(f"Extracting eligibility criteria for {state.program_name}...")

    # Prepare link catalog for prompt
    link_catalog_text = format_link_catalog(state.link_catalog)

    # Prepare screener fields for prompt
    screener_fields_text = format_fields_for_prompt(state.screener_fields)

    # Call LLM to extract and map criteria
    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["extract_criteria"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        link_catalog=link_catalog_text,
        screener_fields=screener_fields_text,
    )

    messages.append("Analyzing documentation with AI...")

    # Check if we have any PDF vision content to send
    # Load content from files
    pdf_vision_content = None
    if state.fetched_content_refs:
        from pathlib import Path

        for url, filepath in state.fetched_content_refs.items():
            try:
                content = Path(filepath).read_text(encoding='utf-8')
                if is_pdf_vision_content(content):
                    pdf_vision_content = (url, content)
                    messages.append(f"  Using vision processing for PDF: {url}")
                    messages.append(f"  Loaded vision data from {filepath}")
                    break
            except Exception as e:
                messages.append(f"  Warning: Could not load {filepath}: {e}")

    # Build the human message content once (multi-modal for PDFs, text otherwise)
    # so we can re-send it verbatim on a parse-retry.
    if pdf_vision_content:
        from ..tools.vision_helper import create_vision_message_content

        url, content_str = pdf_vision_content
        pdf_data = json.loads(content_str)
        human_content = create_vision_message_content(pdf_data, prompt)
    else:
        human_content = prompt

    conversation = [
        SystemMessage(content=RESEARCHER_PROMPTS["system"]),
        HumanMessage(content=human_content),
    ]

    # Extract with one retry: LLMs occasionally wrap the JSON in prose or truncate
    # a fence, which used to silently produce an empty field mapping (the reported
    # "no base criteria" symptom). Retry once with a JSON-only nudge before giving up.
    field_mapping = None
    last_error: Exception | None = None
    raw_response = ""
    for attempt in range(1, 3):
        response = await llm.ainvoke(conversation)
        raw_response = response.content
        if isinstance(raw_response, list):
            raw_response = raw_response[0].get("text", "") if raw_response else ""

        try:
            field_mapping = parse_field_mapping(raw_response, state.program_name)
            break
        except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError) as e:
            last_error = e
            messages.append(f"Attempt {attempt}: could not parse extraction response ({e})")
            if attempt == 1:
                conversation.append(AIMessage(content=raw_response))
                conversation.append(
                    HumanMessage(
                        content=(
                            "Your previous response could not be parsed as JSON. Return ONLY "
                            "the JSON object with keys criteria_can_evaluate, "
                            "criteria_cannot_evaluate, summary, and recommendations — no prose, "
                            "wrapped in a ```json fenced block."
                        )
                    )
                )

    if field_mapping is not None:
        messages.append(
            f"Extracted {len(field_mapping.criteria_can_evaluate)} evaluable criteria, "
            f"{len(field_mapping.criteria_cannot_evaluate)} data gaps"
        )
        messages.append(f"Summary: {field_mapping.summary}")

        return {
            "field_mapping": field_mapping,
            "messages": messages,
        }

    # Both attempts failed — persist the raw response for debugging and surface the
    # error rather than silently emitting an empty spec.
    saved_note = _save_raw_response(state.output_dir, raw_response)
    if saved_note:
        messages.append(saved_note)
    messages.append(f"Error extracting criteria after retries: {last_error}")

    return {
        "field_mapping": FieldMapping(
            program_name=state.program_name,
            summary=f"Error extracting criteria: {last_error}",
        ),
        "messages": messages,
        "error_message": str(last_error),
    }


def format_link_catalog(catalog) -> str:
    """Format the link catalog for inclusion in prompts."""
    if not catalog:
        return "No link catalog available"

    lines = [
        f"## Link Catalog for {catalog.program_name}",
        f"Research Date: {catalog.research_date}",
        f"Sources Provided: {catalog.sources_provided}",
        "",
        "| Category | Title | URL | Source Type | Found In |",
        "|----------|-------|-----|-------------|----------|",
    ]

    for link in catalog.links:
        category = link.category.value if hasattr(link.category, "value") else link.category
        lines.append(
            f"| {category} | {link.title[:50]} | {link.url} | {link.source_type} | {link.found_in} |"
        )

    return "\n".join(lines)
