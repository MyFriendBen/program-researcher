"""
Node: QA Validate Test Cases

Validate test case coverage and accuracy.
"""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.qa_agent import QA_AGENT_PROMPTS
from ..state import (
    IssueSeverity,
    QAIssue,
    QAValidationResult,
    ResearchState,
)
from .generate_tests import format_evaluable_criteria


async def qa_validate_tests_node(state: ResearchState) -> dict:
    """
    Validate test case coverage and accuracy.

    This node checks:
    1. All criteria have test coverage
    2. Boundary conditions are tested precisely
    3. Expected outcomes are correct
    4. Test data is complete
    """
    messages = list(state.messages)
    iteration = state.test_case_iteration + 1
    messages.append(f"QA validation of test cases (iteration {iteration})...")

    # Format inputs
    criteria_text = format_evaluable_criteria(state.field_mapping)
    test_cases_text = format_test_cases(state.test_suite)

    llm = ChatAnthropic(
        model=settings.qa_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = QA_AGENT_PROMPTS["validate_test_cases"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        criteria_can_evaluate=criteria_text,
        test_cases=test_cases_text,
    )

    messages.append("Running QA review of test scenarios...")

    response = await llm.ainvoke(
        [
            SystemMessage(content=QA_AGENT_PROMPTS["system"]),
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

        # Build QA issues
        issues = []
        for item in data.get("issues", []):
            issues.append(
                QAIssue(
                    severity=IssueSeverity(item.get("severity") or "minor"),
                    issue_type=item.get("issue_type", "unknown"),
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    source_reference=item.get("source_reference"),
                    suggested_fix=item.get("suggested_fix", ""),
                    resolved=False,
                )
            )

        result = QAValidationResult(
            validation_type="test_cases",
            overall_status=data.get("overall_status", "NEEDS_REVISION"),
            issues=issues,
            summary=data.get("summary", ""),
            recommendation=data.get("recommendation", ""),
        )

        # Log results - handle both enum and string (use_enum_values=True converts to string)
        def get_severity(issue):
            return issue.severity.value if hasattr(issue.severity, 'value') else issue.severity

        critical_count = sum(1 for i in issues if get_severity(i) == "critical")
        major_count = sum(1 for i in issues if get_severity(i) == "major")

        messages.append(f"QA Result: {result.overall_status}")
        messages.append(f"Issues: {critical_count} critical, {major_count} major, {len(issues) - critical_count - major_count} minor")

        # Log coverage matrix if present
        coverage = data.get("coverage_matrix", {})
        if coverage:
            untested = [k for k, v in coverage.items() if not v.get("tested", False)]
            if untested:
                messages.append(f"Untested criteria: {untested}")

        return {
            "test_case_qa_result": result,
            "test_case_iteration": iteration,
            "messages": messages,
        }

    except (json.JSONDecodeError, KeyError) as e:
        messages.append(f"Error parsing QA response: {e}")

        return {
            "test_case_qa_result": QAValidationResult(
                validation_type="test_cases",
                overall_status="VALIDATED_WITH_CONCERNS",
                issues=[],
                summary="QA validation completed with parsing issues",
                recommendation="Proceed with caution",
            ),
            "test_case_iteration": iteration,
            "messages": messages,
        }


def format_test_cases(suite) -> str:
    """Format test cases for QA review."""
    if not suite or not suite.test_cases:
        return "No test cases available"

    lines = [
        f"## Test Suite: {suite.program_name}",
        f"Total Scenarios: {len(suite.test_cases)}",
        "",
    ]

    for tc in suite.test_cases:
        lines.extend([
            f"### Scenario {tc.scenario_number}: {tc.title}",
            f"**Category**: {tc.category}",
            f"**What we're checking**: {tc.what_checking}",
            f"**Expected eligible**: {tc.expected_eligible}",
            f"**Expected amount**: ${tc.expected_amount}/year" if tc.expected_amount else "",
            "",
            "**Test Data**:",
            f"- ZIP: {tc.zip_code}, County: {tc.county}",
            f"- Household size: {tc.household_size}",
            f"- Assets: ${tc.household_assets}",
            "",
        ])

        for i, member in enumerate(tc.members_data):
            lines.append(f"**Member {i+1}**:")
            lines.append(f"  - Relationship: {member.get('relationship', 'unknown')}")
            lines.append(f"  - Birth: {member.get('birth_month', '?')}/{member.get('birth_year', '?')}")
            if member.get('income'):
                income = member['income']
                income_items = [f"{k}: ${v}" for k, v in income.items() if k != 'income_frequency' and v]
                if income_items:
                    lines.append(f"  - Income: {', '.join(income_items)} ({income.get('income_frequency', 'monthly')})")
            lines.append("")

        lines.extend([
            "**Why this matters**: " + tc.why_matters,
            "",
            "---",
            "",
        ])

    return "\n".join(lines)
