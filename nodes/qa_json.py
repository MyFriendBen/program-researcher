"""
Node: QA Validate JSON

Validate JSON test cases match human-readable scenarios.
"""

import json
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_schema_path, settings
from ..prompts.qa_agent import QA_AGENT_PROMPTS
from ..state import (
    IssueSeverity,
    QAIssue,
    QAValidationResult,
    ResearchState,
)
from ..tools.schema_validator import validate_test_batch
from .qa_tests import format_test_cases


async def qa_validate_json_node(state: ResearchState) -> dict:
    """
    Validate JSON test cases match human-readable scenarios.

    This node checks:
    1. Schema compliance
    2. Data accuracy vs human-readable source
    3. Correct field mapping
    4. Age calculations
    """
    messages = list(state.messages)
    iteration = state.json_iteration + 1
    messages.append(f"QA validation of JSON output (iteration {iteration})...")

    if not state.json_test_cases:
        messages.append("No JSON test cases to validate")
        return {
            "json_qa_result": QAValidationResult(
                validation_type="json",
                overall_status="NEEDS_REVISION",
                issues=[
                    QAIssue(
                        severity=IssueSeverity.CRITICAL,
                        issue_type="missing_data",
                        description="No JSON test cases generated",
                        location="json_test_cases",
                        suggested_fix="Re-run JSON conversion",
                    )
                ],
                summary="No JSON test cases to validate",
                recommendation="Fix JSON conversion first",
            ),
            "json_iteration": iteration,
            "messages": messages,
        }

    # First, validate against schema
    json_data = [tc.model_dump() for tc in state.json_test_cases]
    is_valid, schema_errors = validate_test_batch(json_data)

    issues = []
    if not is_valid:
        for error in schema_errors[:10]:  # Limit to first 10 errors
            issues.append(
                QAIssue(
                    severity=IssueSeverity.CRITICAL,
                    issue_type="schema_violation",
                    description=error,
                    location="json_test_cases",
                    suggested_fix="Fix schema compliance issue",
                )
            )

    # Load schema for LLM reference
    schema_path = get_schema_path("pre_validation_schema.json")
    with open(schema_path) as f:
        schema = json.load(f)

    # Format for LLM validation
    human_test_cases_text = format_test_cases(state.test_suite)
    json_test_cases_text = json.dumps(json_data, indent=2)

    llm = ChatAnthropic(
        model=settings.qa_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        api_key=settings.anthropic_api_key,
    )

    prompt = QA_AGENT_PROMPTS["validate_json"].format(
        human_test_cases=human_test_cases_text,
        json_test_cases=json_test_cases_text,
        json_schema=json.dumps(schema, indent=2)[:5000],  # Truncate schema
        current_date=date.today().isoformat(),
    )

    messages.append("Comparing JSON output to human-readable source...")

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

        # Add LLM-identified issues
        for item in data.get("issues", []):
            issues.append(
                QAIssue(
                    severity=IssueSeverity(item.get("severity", "minor")),
                    issue_type=item.get("issue_type", "unknown"),
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    source_reference=item.get("source_reference"),
                    suggested_fix=item.get("suggested_fix", ""),
                    resolved=False,
                )
            )

        # Determine overall status - handle both enum and string (use_enum_values=True converts to string)
        def get_severity(issue):
            return issue.severity.value if hasattr(issue.severity, 'value') else issue.severity

        critical_issues = [i for i in issues if get_severity(i) == "critical"]
        major_issues = [i for i in issues if get_severity(i) == "major"]

        if critical_issues:
            overall_status = "NEEDS_REVISION"
        elif major_issues:
            overall_status = "VALIDATED_WITH_CONCERNS"
        else:
            overall_status = "VALIDATED"

        result = QAValidationResult(
            validation_type="json",
            overall_status=data.get("overall_status", overall_status),
            issues=issues,
            summary=data.get("summary", f"Validated {len(state.json_test_cases)} test cases"),
            recommendation=data.get("recommendation", "Proceed" if not critical_issues else "Fix issues first"),
        )

        messages.append(f"QA Result: {result.overall_status}")
        messages.append(f"Issues: {len(critical_issues)} critical, {len(major_issues)} major")

        return {
            "json_qa_result": result,
            "json_iteration": iteration,
            "messages": messages,
        }

    except (json.JSONDecodeError, KeyError) as e:
        messages.append(f"Error parsing QA response: {e}")

        # Return result based on schema validation alone
        overall_status = "VALIDATED" if is_valid else "NEEDS_REVISION"

        return {
            "json_qa_result": QAValidationResult(
                validation_type="json",
                overall_status=overall_status,
                issues=issues,
                summary=f"Schema validation: {'passed' if is_valid else 'failed'}",
                recommendation="Proceed" if is_valid else "Fix schema issues",
            ),
            "json_iteration": iteration,
            "messages": messages,
        }
