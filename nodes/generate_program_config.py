"""
Node: Generate Program Configuration

Generate Django admin import configuration JSON for the program.
This creates the initial_config.json format used by the
import_program_config_data management command.
"""

from typing import Optional

from langchain_anthropic import ChatAnthropic

from ..config import settings
from ..prompts.researcher import GENERATE_PROGRAM_CONFIG_PROMPT
from ..state import ProgramConfig, ResearchState


async def generate_program_config_node(state: ResearchState) -> dict:
    """
    Generate Django admin import configuration.

    This node:
    1. Analyzes research data and source documentation
    2. Generates program metadata (name, description, etc.)
    3. Extracts application links and navigator contacts
    4. Identifies required documents
    5. Determines legal status requirements
    6. Creates config in import_program_config_data format
    """
    messages = list(state.messages)
    messages.append("Generating program configuration for admin import...")

    # Validate required data exists
    if not state.field_mapping:
        messages.append("Warning: No field mapping available - config may be incomplete")

    if not state.link_catalog:
        messages.append("Warning: No source links - using provided URLs only")

    # Build the research context for the LLM
    research_context = build_research_context(state)

    # Call LLM to generate config
    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=0,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = GENERATE_PROGRAM_CONFIG_PROMPT.format(
        program_name=state.program_name.lower(),
        state_code=state.state_code,
        white_label=state.white_label,
        research_context=research_context,
    )

    response = await llm.ainvoke(prompt)
    config_json = response.content

    # Clean up response - remove markdown code blocks if present
    import json
    import re

    # Remove markdown code fences if present
    config_json_cleaned = config_json.strip()
    if config_json_cleaned.startswith("```"):
        # Extract content between code fences
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", config_json_cleaned, re.DOTALL)
        if match:
            config_json_cleaned = match.group(1)
        else:
            # Try removing just the first and last lines
            lines = config_json_cleaned.split("\n")
            if lines[0].startswith("```") and lines[-1].strip() == "```":
                config_json_cleaned = "\n".join(lines[1:-1])

    # Parse and validate the config
    try:
        config_dict = json.loads(config_json_cleaned)
        program_config = ProgramConfig(**config_dict)
        messages.append("✓ Program configuration generated successfully")
        messages.append(f"  - Name: {config_dict.get('program', {}).get('name', 'N/A')}")
        messages.append(f"  - Category: {config_dict.get('program_category', {}).get('external_name', 'N/A')}")

        # Validate key fields
        validation_warnings = []
        if not program_config.program.get("description"):
            validation_warnings.append("Missing program description")
        if not program_config.program.get("apply_button_link"):
            validation_warnings.append("Missing application link")
        if not program_config.documents:
            validation_warnings.append("No required documents specified")

        if validation_warnings:
            messages.append("⚠️  Configuration warnings:")
            for warning in validation_warnings:
                messages.append(f"  - {warning}")
            messages.append("Human should review and complete these fields in Linear ticket")

        return {
            "program_config": program_config,
            "messages": messages,
        }

    except json.JSONDecodeError as e:
        messages.append(f"❌ Error parsing config JSON: {e}")
        messages.append(f"   Raw response length: {len(config_json)} characters")
        messages.append(f"   First 200 chars: {config_json[:200]}")
        messages.append("   Creating minimal config structure as fallback...")

        # Fallback: Create minimal config
        minimal_config = create_minimal_config(state)

        return {
            "program_config": minimal_config,
            "messages": messages,
        }
    except Exception as e:
        messages.append(f"❌ Error validating config: {e}")
        messages.append(f"   Config dict keys: {list(config_dict.keys()) if 'config_dict' in locals() else 'N/A'}")
        messages.append("   Creating minimal config structure as fallback...")

        minimal_config = create_minimal_config(state)

        return {
            "program_config": minimal_config,
            "messages": messages,
        }


def build_research_context(state: ResearchState) -> str:
    """Build research context for the LLM with all available data."""
    context_parts = []

    # Add comprehensive program information from field mapping
    if state.field_mapping and state.field_mapping.summary:
        context_parts.append("## Program Overview")
        context_parts.append("")
        context_parts.append(state.field_mapping.summary)
        context_parts.append("")

    # Add source URLs with detailed info from link catalog
    context_parts.append("## Source Documentation")
    context_parts.append("")
    context_parts.append("**Primary Sources:**")
    for url in state.source_urls:
        context_parts.append(f"- {url}")

    # Add links from catalog that might have application info
    if state.link_catalog:
        context_parts.append("")
        context_parts.append("**Additional Resources Found:**")
        for link in state.link_catalog.links[:30]:
            # Include official sources, application pages, and policy docs
            if link.category in ["Official Program", "Application", "Policy"]:
                context_parts.append(f"- [{link.title}]({link.url})")
                if link.content_summary:
                    context_parts.append(f"  Summary: {link.content_summary}")
    context_parts.append("")

    # Add detailed eligibility criteria
    if state.field_mapping:
        context_parts.append("## Detailed Eligibility Criteria")
        context_parts.append("")
        for i, criterion in enumerate(state.field_mapping.criteria_can_evaluate, 1):
            context_parts.append(f"{i}. {criterion.criterion}")
            if criterion.evaluation_logic:
                context_parts.append(f"   Logic: {criterion.evaluation_logic}")
            if criterion.source_reference:
                context_parts.append(f"   Source: {criterion.source_reference}")
            if criterion.notes:
                context_parts.append(f"   Notes: {criterion.notes}")
            context_parts.append("")

        # Add data gaps with recommendations
        if state.field_mapping.criteria_cannot_evaluate:
            context_parts.append("## Known Limitations")
            context_parts.append("")
            for criterion in state.field_mapping.criteria_cannot_evaluate:
                context_parts.append(f"- {criterion.criterion}")
                if criterion.notes:
                    context_parts.append(f"  Note: {criterion.notes}")
                context_parts.append(f"  Impact: {criterion.impact}")
            context_parts.append("")

        # Add recommendations for implementation
        if state.field_mapping.recommendations:
            context_parts.append("## Implementation Recommendations")
            context_parts.append("")
            for rec in state.field_mapping.recommendations:
                context_parts.append(f"- {rec}")
            context_parts.append("")

    # Add test case details for benefit estimates and scenarios
    if state.test_suite and state.test_suite.test_cases:
        context_parts.append("## Test Scenarios (for benefit value context)")
        context_parts.append("")

        eligible_test = next((tc for tc in state.test_suite.test_cases if tc.expected_eligible), None)
        if eligible_test:
            context_parts.append(f"**Eligible Example:** {eligible_test.title}")
            context_parts.append(f"- Expected benefit: ${eligible_test.expected_amount}/year")
            context_parts.append(f"- Scenario: {eligible_test.what_checking}")
            context_parts.append("")

    return "\n".join(context_parts)


def create_minimal_config(state: ResearchState) -> ProgramConfig:
    """Create a minimal config structure as fallback."""
    program_name_clean = state.program_name.replace("_", " ").title()

    return ProgramConfig(
        white_label={"code": state.white_label},
        program_category={"external_name": f"{state.white_label}_food"},  # Default to food category
        program={
            "name_abbreviated": f"{state.white_label}_{state.program_name.lower()}",
            "year": "2025",
            "legal_status_required": ["citizen"],  # Default - human should review
            "name": program_name_clean,
            "description": f"{program_name_clean} - Description needed. See research documentation.",
            "learn_more_link": state.source_urls[0] if state.source_urls else "",
            "apply_button_link": "",  # Human should fill in
            "apply_button_description": "Learn More and Apply",
            "estimated_application_time": "Varies",
            "estimated_delivery_time": "",
            "estimated_value": "",
        },
        documents=[
            {
                "external_name": f"{state.white_label}_home",
                "text": "Proof of home address",
                "link_url": "",
                "link_text": "",
            },
            {
                "external_name": "id_proof",
                "text": "Proof of identity",
                "link_url": "",
                "link_text": "",
            },
        ],
        navigators=[],  # Human should add local contacts
    )
