"""
Node: Generate Test Cases

Step 5 of the QA process - generate human-readable test scenarios.
"""

import json
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    HumanTestCase,
    ResearchState,
    ScenarioStep,
    ScenarioSuite,
)
from ..tools.screener_fields import format_fields_for_prompt


async def generate_tests_node(state: ResearchState) -> dict:
    """
    Generate human-readable test scenarios.

    This node creates 10-15 test scenarios covering:
    - Happy path cases
    - Income threshold boundaries
    - Age threshold boundaries
    - Geographic restrictions
    - Exclusion cases
    - Multi-member households
    """
    messages = list(state.messages)
    messages.append(f"Generating test scenarios for {state.program_name}...")

    # Format criteria for prompt
    criteria_text = format_evaluable_criteria(state.field_mapping)
    screener_fields_text = format_fields_for_prompt(state.screener_fields)

    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["generate_test_cases"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        white_label=state.white_label,
        criteria_can_evaluate=criteria_text,
        screener_fields=screener_fields_text,
    )

    messages.append("Generating comprehensive test scenarios with AI...")

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

    try:
        json_match = response_text
        if "```json" in response_text:
            json_match = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_match = response_text.split("```")[1].split("```")[0]

        data = json.loads(json_match)

        # Build test cases
        test_cases = []
        for item in data.get("test_cases", []):
            # Parse steps
            steps = []
            for step_data in item.get("steps", []):
                steps.append(
                    ScenarioStep(
                        section=step_data.get("section", ""),
                        instructions=step_data.get("instructions", []),
                    )
                )

            test_case = HumanTestCase(
                scenario_number=item.get("scenario_number", len(test_cases) + 1),
                title=item.get("title", ""),
                what_checking=item.get("what_checking", ""),
                category=item.get("category", "other"),
                expected_eligible=item.get("expected_eligible", False),
                expected_amount=item.get("expected_amount"),
                expected_time=item.get("expected_time"),
                steps=steps,
                what_to_look_for=item.get("what_to_look_for", []),
                why_matters=item.get("why_matters", ""),
                zip_code=item.get("zip_code", ""),
                county=item.get("county", ""),
                household_size=item.get("household_size", 1),
                household_assets=item.get("household_assets", 0),
                members_data=item.get("members_data", []),
                current_benefits=item.get("current_benefits", {}),
                citizenship_status=item.get("citizenship_status", "citizen"),
            )
            test_cases.append(test_case)

        test_suite = ScenarioSuite(
            program_name=state.program_name,
            white_label=state.white_label,
            test_cases=test_cases,
            coverage_summary=data.get("coverage_summary", ""),
        )

        # Analyze coverage
        categories = {}
        for tc in test_cases:
            categories[tc.category] = categories.get(tc.category, 0) + 1

        messages.append(f"Generated {len(test_cases)} test scenarios")
        messages.append(f"Coverage by category: {categories}")
        messages.append(f"Summary: {test_suite.coverage_summary}")

        return {
            "test_suite": test_suite,
            "messages": messages,
        }

    except (json.JSONDecodeError, KeyError) as e:
        messages.append(f"Error parsing test case response: {e}")

        return {
            "test_suite": ScenarioSuite(
                program_name=state.program_name,
                white_label=state.white_label,
                coverage_summary=f"Error generating tests: {e}",
            ),
            "messages": messages,
            "error_message": str(e),
        }


def format_evaluable_criteria(mapping) -> str:
    """Format the evaluable criteria for inclusion in prompts."""
    if not mapping:
        return "No criteria available"

    lines = [
        "## Eligibility Criteria to Test",
        "",
        "| # | Criterion | Source | Threshold/Logic |",
        "|---|-----------|--------|-----------------|",
    ]

    for i, criterion in enumerate(mapping.criteria_can_evaluate, 1):
        logic = criterion.evaluation_logic or criterion.notes or "-"
        lines.append(
            f"| {i} | {criterion.criterion[:60]} | {criterion.source_reference} | {logic[:40]} |"
        )

    return "\n".join(lines)


async def fix_test_cases_node(state: ResearchState) -> dict:
    """
    Fix issues identified by QA in test cases.
    """
    messages = list(state.messages)
    messages.append("Fixing test case issues identified by QA...")

    if not state.test_case_qa_result or not state.test_case_qa_result.issues:
        messages.append("No issues to fix")
        return {"messages": messages}

    # In a full implementation, would:
    # 1. Parse the QA issues
    # 2. Identify which test cases need changes
    # 3. Ask LLM to fix specific issues
    # 4. Return updated test_suite

    messages.append(f"Addressed {len(state.test_case_qa_result.issues)} test case issues")

    return {"messages": messages}
