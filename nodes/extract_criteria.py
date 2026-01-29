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
    EligibilityCriterion,
    FieldMapping,
    ImpactLevel,
    ResearchState,
)
from ..tools.screener_fields import format_fields_for_prompt


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
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["extract_criteria"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        link_catalog=link_catalog_text,
        screener_fields=screener_fields_text,
    )

    messages.append("Analyzing documentation with AI...")

    response = await llm.ainvoke(
        [
            SystemMessage(content=RESEARCHER_PROMPTS["system"]),
            HumanMessage(content=prompt),
        ]
    )

    # Parse response
    response_text = response.content
    if isinstance(response_text, list):
        response_text = response_text[0].get("text", "") if response_text else ""

    # Extract JSON from response
    try:
        json_match = response_text
        if "```json" in response_text:
            json_match = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_match = response_text.split("```")[1].split("```")[0]

        data = json.loads(json_match)

        # Build criteria objects
        criteria_can_evaluate = []
        for item in data.get("criteria_can_evaluate", []):
            criteria_can_evaluate.append(
                EligibilityCriterion(
                    criterion=item.get("criterion", ""),
                    source_reference=item.get("source_reference", ""),
                    source_url=item.get("source_url"),
                    screener_fields=item.get("screener_fields"),
                    evaluation_logic=item.get("evaluation_logic"),
                    notes=item.get("notes", ""),
                    impact=ImpactLevel(item.get("impact", "Medium")),
                )
            )

        criteria_cannot_evaluate = []
        for item in data.get("criteria_cannot_evaluate", []):
            criteria_cannot_evaluate.append(
                EligibilityCriterion(
                    criterion=item.get("criterion", ""),
                    source_reference=item.get("source_reference", ""),
                    source_url=item.get("source_url"),
                    screener_fields=None,
                    evaluation_logic=None,
                    notes=item.get("notes", ""),
                    impact=ImpactLevel(item.get("impact", "Medium")),
                )
            )

        field_mapping = FieldMapping(
            program_name=state.program_name,
            criteria_can_evaluate=criteria_can_evaluate,
            criteria_cannot_evaluate=criteria_cannot_evaluate,
            summary=data.get("summary", ""),
            recommendations=data.get("recommendations", []),
        )

        messages.append(
            f"Extracted {len(criteria_can_evaluate)} evaluable criteria, "
            f"{len(criteria_cannot_evaluate)} data gaps"
        )
        messages.append(f"Summary: {field_mapping.summary}")

        return {
            "field_mapping": field_mapping,
            "messages": messages,
        }

    except (json.JSONDecodeError, KeyError) as e:
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
