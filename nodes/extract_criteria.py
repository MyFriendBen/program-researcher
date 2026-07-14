"""
Node: Extract Criteria

Step 3 of the QA process - extract eligibility criteria and map to screener fields.
"""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    FieldMapping,
    ResearchState,
)
from ..tools.screener_fields import format_fields_for_prompt
from ..tools.vision_helper import is_pdf_vision_content


def normalize_field_mapping(program_name: str, mapping: FieldMapping) -> FieldMapping:
    """Normalize a model-produced FieldMapping.

    Shared by extract_criteria_node and fix_research_node: the program_name is
    taken from state (never trusted from the model), and criteria_cannot_evaluate
    are data gaps, so their screener_fields/evaluation_logic are forced to None.
    Impact-level case coercion is handled by EligibilityCriterion's validator.
    """
    for criterion in mapping.criteria_cannot_evaluate:
        criterion.screener_fields = None
        criterion.evaluation_logic = None
    mapping.program_name = program_name
    return mapping


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

    # Call LLM to extract and map criteria. The model returns a FieldMapping
    # directly via structured output (forced tool call), so there is no fenced
    # JSON to hand-parse.
    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    ).with_structured_output(FieldMapping)

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

    # Build message content
    if pdf_vision_content:
        from ..tools.vision_helper import create_vision_message_content

        url, content_str = pdf_vision_content
        pdf_data = json.loads(content_str)

        # Create multi-modal message with text + images
        message_content = create_vision_message_content(pdf_data, prompt)
        request = [
            SystemMessage(content=RESEARCHER_PROMPTS["system"]),
            HumanMessage(content=message_content),
        ]
    else:
        # Regular text-only message
        request = [
            SystemMessage(content=RESEARCHER_PROMPTS["system"]),
            HumanMessage(content=prompt),
        ]

    # The model returns a validated FieldMapping (or raises if it cannot produce
    # one). Any failure yields an empty mapping so downstream QA can re-flag.
    try:
        field_mapping = await llm.ainvoke(request)
        field_mapping = normalize_field_mapping(state.program_name, field_mapping)
    except Exception as e:
        messages.append(f"Error parsing LLM response: {e}")
        messages.append("Raw response saved for debugging")

        # Return empty mapping
        return {
            "field_mapping": FieldMapping(
                program_name=state.program_name,
                summary=f"Error extracting criteria: {e}",
            ),
            "messages": messages,
            "error_message": str(e),
        }

    messages.append(
        f"Extracted {len(field_mapping.criteria_can_evaluate)} evaluable criteria, "
        f"{len(field_mapping.criteria_cannot_evaluate)} data gaps"
    )
    messages.append(f"Summary: {field_mapping.summary}")

    return {
        "field_mapping": field_mapping,
        "messages": messages,
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
