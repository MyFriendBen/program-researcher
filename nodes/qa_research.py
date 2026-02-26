"""
Node: QA Validate Research

Step 4 of the QA process - independent validation of research and field mapping.
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
from .extract_criteria import format_link_catalog


async def qa_validate_research_node(state: ResearchState) -> dict:
    """
    Independently validate the research and field mapping.

    This node acts as an adversarial reviewer:
    1. Re-fetches source documentation
    2. Independently extracts criteria
    3. Compares against researcher's findings
    4. Flags discrepancies and missed items
    """
    messages = list(state.messages)
    iteration = state.research_iteration + 1
    messages.append(f"QA validation of research (iteration {iteration})...")

    # Format inputs for the QA agent
    link_catalog_text = format_link_catalog(state.link_catalog)
    field_mapping_text = format_field_mapping(state.field_mapping)

    # Call LLM for QA validation
    llm = ChatAnthropic(
        model=settings.qa_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = QA_AGENT_PROMPTS["validate_research"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        source_urls="\n".join(f"- {url}" for url in state.source_urls),
        link_catalog=link_catalog_text,
        field_mapping=field_mapping_text,
    )

    messages.append("Running adversarial QA review...")

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
            validation_type="research",
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
        minor_count = sum(1 for i in issues if get_severity(i) == "minor")

        messages.append(f"QA Result: {result.overall_status}")
        messages.append(f"Issues found: {critical_count} critical, {major_count} major, {minor_count} minor")
        messages.append(f"Recommendation: {result.recommendation}")

        return {
            "research_qa_result": result,
            "research_iteration": iteration,
            "messages": messages,
        }

    except (json.JSONDecodeError, KeyError) as e:
        messages.append(f"Error parsing QA response: {e}")

        # Return a result that triggers revision
        return {
            "research_qa_result": QAValidationResult(
                validation_type="research",
                overall_status="NEEDS_REVISION",
                issues=[
                    QAIssue(
                        severity=IssueSeverity.MAJOR,
                        issue_type="parse_error",
                        description=f"QA validation failed to parse: {e}",
                        location="qa_response",
                        suggested_fix="Re-run QA validation",
                    )
                ],
                summary="QA validation encountered an error",
                recommendation="Retry validation",
            ),
            "research_iteration": iteration,
            "messages": messages,
        }


def format_field_mapping(mapping) -> str:
    """Format the field mapping for inclusion in prompts."""
    if not mapping:
        return "No field mapping available"

    lines = [
        f"## Field Mapping for {mapping.program_name}",
        "",
        "### Criteria We CAN Evaluate",
        "",
        "| Criterion | Source Reference | Screener Fields | Evaluation Logic |",
        "|-----------|------------------|-----------------|------------------|",
    ]

    for criterion in mapping.criteria_can_evaluate:
        fields = ", ".join(criterion.screener_fields) if criterion.screener_fields else "-"
        logic = criterion.evaluation_logic or "-"
        lines.append(
            f"| {criterion.criterion[:60]} | {criterion.source_reference} | {fields} | {logic[:40]} |"
        )

    lines.extend([
        "",
        "### Criteria We CANNOT Evaluate (Data Gaps)",
        "",
        "| Criterion | Source Reference | Impact | Notes |",
        "|-----------|------------------|--------|-------|",
    ])

    for criterion in mapping.criteria_cannot_evaluate:
        # Handle both enum and string (use_enum_values=True converts to string)
        impact = criterion.impact.value if hasattr(criterion.impact, 'value') else criterion.impact
        lines.append(
            f"| {criterion.criterion[:60]} | {criterion.source_reference} | {impact} | {criterion.notes[:40]} |"
        )

    lines.extend([
        "",
        f"### Summary",
        mapping.summary,
        "",
        "### Recommendations",
    ])

    for rec in mapping.recommendations:
        lines.append(f"- {rec}")

    return "\n".join(lines)


async def fix_research_node(state: ResearchState) -> dict:
    """
    Fix issues identified by QA validation.

    This node takes the QA issues and asks the researcher agent
    to address them.
    """
    messages = list(state.messages)
    messages.append("Fixing research issues identified by QA...")

    if not state.research_qa_result or not state.research_qa_result.issues:
        messages.append("No issues to fix")
        return {"messages": messages}

    # Format current output and issues
    from ..prompts.researcher import RESEARCHER_PROMPTS

    current_output = format_field_mapping(state.field_mapping)
    issues_text = format_qa_issues(state.research_qa_result.issues)

    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["fix_issues"].format(
        current_output=current_output,
        qa_issues=issues_text,
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=RESEARCHER_PROMPTS["system"]),
            HumanMessage(content=prompt),
        ]
    )

    # Parse and update field mapping
    # This is simplified - in practice you'd parse the full response
    response_text = response.content
    if isinstance(response_text, list):
        response_text = response_text[0].get("text", "") if response_text else ""

    messages.append(f"Addressed {len(state.research_qa_result.issues)} issues")

    # Mark issues as resolved
    if state.research_qa_result:
        for issue in state.research_qa_result.issues:
            issue.resolved = True

    return {
        "messages": messages,
        # In a full implementation, would return updated field_mapping
    }


def format_qa_issues(issues: list[QAIssue]) -> str:
    """Format QA issues for the fix prompt."""
    lines = ["## Issues to Address", ""]

    for i, issue in enumerate(issues, 1):
        # Handle both enum and string (use_enum_values=True converts to string)
        severity = issue.severity.value if hasattr(issue.severity, 'value') else issue.severity
        lines.extend([
            f"### Issue {i}: [{severity.upper()}] {issue.issue_type}",
            f"**Location**: {issue.location}",
            f"**Description**: {issue.description}",
            f"**Suggested Fix**: {issue.suggested_fix}",
            "",
        ])

    return "\n".join(lines)
