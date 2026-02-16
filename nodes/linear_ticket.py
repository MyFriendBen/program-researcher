"""
Node: Create Linear Ticket

Create a Linear ticket with acceptance criteria and test scenarios.
"""

import json
from datetime import date

import httpx

from ..config import get_output_path, settings
from ..state import (
    LinearTicketContent,
    ResearchState,
    WorkflowStatus,
)


async def create_linear_ticket_node(state: ResearchState) -> dict:
    """
    Create a Linear ticket with acceptance criteria.

    This node:
    1. Validates required data exists
    2. Formats the acceptance criteria from test cases
    3. Includes field mapping summary
    4. Attaches JSON test cases as reference
    5. Creates the ticket via Linear API
    """
    messages = list(state.messages)
    messages.append("Creating Linear ticket...")

    # Validate required data exists
    validation_errors = []

    if not state.field_mapping:
        validation_errors.append("Missing field mapping - research extraction may have failed")

    if not state.test_suite or not state.test_suite.test_cases:
        validation_errors.append("Missing test cases - test generation may have failed")

    if not state.json_test_cases:
        validation_errors.append("Missing JSON test cases - JSON conversion may have failed")

    if validation_errors:
        messages.append("Validation failed - cannot create complete ticket:")
        for error in validation_errors:
            messages.append(f"  - {error}")

        return {
            "linear_ticket": None,
            "linear_ticket_url": None,
            "linear_ticket_id": None,
            "status": WorkflowStatus.FAILED,
            "error_message": "Cannot create ticket: " + "; ".join(validation_errors),
            "messages": messages,
        }

    # Build ticket content
    ticket_content = build_ticket_content(state)

    # Save JSON test cases to file
    json_file_path = None
    if state.json_test_cases:
        json_file_path = save_json_test_cases(state)
        messages.append(f"Saved JSON test cases to {json_file_path}")

    # Save program config to file
    config_file_path = None
    if state.program_config:
        config_file_path = save_program_config(state)
        messages.append(f"Saved program config to {config_file_path}")

    ticket_content.json_test_file_path = str(json_file_path) if json_file_path else None
    ticket_content.program_config_file_path = str(config_file_path) if config_file_path else None

    # Create ticket via Linear API (if configured)
    ticket_url = None
    ticket_id = None

    if settings.linear_api_key and settings.linear_team_id:
        try:
            ticket_url, ticket_id = await create_linear_issue(ticket_content)
            messages.append(f"Created Linear ticket: {ticket_url}")
        except Exception as e:
            messages.append(f"Error creating Linear ticket: {e}")
            messages.append("Ticket content saved locally instead")
    else:
        messages.append("Linear API not configured - saving ticket content locally")
        save_ticket_content_locally(ticket_content, state)

    messages.append("Workflow complete!")

    return {
        "linear_ticket": ticket_content,
        "linear_ticket_url": ticket_url,
        "linear_ticket_id": ticket_id,
        "status": WorkflowStatus.COMPLETED,
        "messages": messages,
    }


def build_ticket_content(state: ResearchState) -> LinearTicketContent:
    """Build the ticket content from state."""

    # Title
    title = f"Implement {state.program_name} ({state.state_code.upper()}) Program"

    # Description
    description_parts = [
        "## Program Details",
        "",
        f"- **Program**: {state.program_name}",
        f"- **State**: {state.state_code.upper()}",
        f"- **White Label**: {state.white_label}",
        f"- **Research Date**: {date.today().isoformat()}",
        "",
    ]

    # Add eligibility criteria with screener field mappings
    if state.field_mapping and state.field_mapping.criteria_can_evaluate:
        description_parts.extend([
            "## Eligibility Criteria",
            "",
        ])

        for i, criterion in enumerate(state.field_mapping.criteria_can_evaluate, 1):
            description_parts.extend([
                f"{i}. **{criterion.criterion}**",
            ])

            # Add screener field details
            if criterion.screener_fields:
                description_parts.append("   - Screener fields:")
                for field in criterion.screener_fields:
                    description_parts.append(f"     - `{field}`")

            # Add evaluation logic if available
            if criterion.evaluation_logic:
                description_parts.append(f"   - Logic: `{criterion.evaluation_logic}`")

            # Add source reference
            if criterion.source_reference:
                description_parts.append(f"   - Source: {criterion.source_reference}")

            description_parts.append("")

    # Add benefit value information if available
    description_parts.extend([
        "## Benefit Value",
        "",
    ])

    # Try to extract benefit amount from test cases
    if state.test_suite and state.test_suite.test_cases:
        eligible_test = next((tc for tc in state.test_suite.test_cases if tc.expected_eligible), None)
        if eligible_test and eligible_test.expected_amount:
            description_parts.append(f"- **Estimated Annual Value**: ${eligible_test.expected_amount}/year")
            description_parts.append("- See test cases for calculation details")
        else:
            description_parts.append("- Amount varies by household - see test cases")
    else:
        description_parts.append("- See research documentation for benefit amounts")

    description_parts.append("")

    # Add data gaps (critical for implementation)
    if state.field_mapping and state.field_mapping.criteria_cannot_evaluate:
        description_parts.extend([
            "## Data Gaps",
            "",
            "⚠️  The following criteria cannot be fully evaluated with current screener fields:",
            "",
        ])

        for i, criterion in enumerate(state.field_mapping.criteria_cannot_evaluate, 1):
            description_parts.extend([
                f"{i}. **{criterion.criterion}**",
            ])

            if criterion.notes:
                description_parts.append(f"   - Note: {criterion.notes}")

            if criterion.source_reference:
                description_parts.append(f"   - Source: {criterion.source_reference}")

            description_parts.append(f"   - Impact: {criterion.impact}")
            description_parts.append("")

    # Add field mapping summary
    if state.field_mapping:
        description_parts.extend([
            "## Implementation Coverage",
            "",
            f"- ✅ Evaluable criteria: {len(state.field_mapping.criteria_can_evaluate)}",
            f"- ⚠️  Data gaps: {len(state.field_mapping.criteria_cannot_evaluate)}",
            "",
            state.field_mapping.summary,
            "",
        ])

    # Add source documentation
    description_parts.append("## Research Sources")
    description_parts.append("")
    if state.link_catalog:
        for link in state.link_catalog.links[:10]:
            description_parts.append(f"- [{link.title}]({link.url})")
    description_parts.append("")

    # Add program configuration JSON (embed in ticket)
    if state.program_config:
        config_json = json.dumps(state.program_config.model_dump(), indent=2)
        description_parts.extend([
            "## Program Configuration",
            "",
            "Django admin import configuration (ready to use):",
            "",
            "```json",
            config_json,
            "```",
            "",
            "**Human Review Checklist:**",
            "- [ ] Verify program name and description are accurate",
            "- [ ] Confirm application link is correct",
            "- [ ] Add navigator contacts if available",
            "- [ ] Review required documents list",
            "- [ ] Check legal status requirements",
            "",
        ])

    # Add reference to local research output
    if state.output_dir:
        description_parts.extend([
            "## Research Output",
            "",
            f"Local path: `{state.output_dir}`",
            "",
            "Files generated:",
            "- Program config: `{white_label}_{program_name}_initial_config.json`",
            "- Test cases: `{white_label}_{program_name}_test_cases.json`",
            "- Full research data in output directory",
            "",
        ])

    description = "\n".join(description_parts)

    # Acceptance criteria from test cases
    acceptance_criteria = []
    if state.test_suite:
        for tc in state.test_suite.test_cases:
            if tc.expected_eligible:
                criteria = f"[ ] Scenario {tc.scenario_number} ({tc.title}): User should be **eligible** with ${tc.expected_amount}/year"
            else:
                criteria = f"[ ] Scenario {tc.scenario_number} ({tc.title}): User should be **ineligible**"
            acceptance_criteria.append(criteria)

    # Test scenarios summary
    test_summary_parts = ["## Test Scenarios", ""]
    if state.test_suite:
        for tc in state.test_suite.test_cases:
            test_summary_parts.extend([
                f"### Scenario {tc.scenario_number}: {tc.title}",
                f"**What we're checking**: {tc.what_checking}",
                f"**Expected**: {'Eligible' if tc.expected_eligible else 'Not eligible'}",
                "",
                "**Steps**:",
            ])
            for step in tc.steps:
                test_summary_parts.append(f"- **{step.section}**: {', '.join(step.instructions)}")
            test_summary_parts.extend([
                "",
                f"**Why this matters**: {tc.why_matters}",
                "",
                "---",
                "",
            ])

    test_scenarios_summary = "\n".join(test_summary_parts)

    # Source documentation URLs
    source_docs = []
    if state.link_catalog:
        source_docs = [link.url for link in state.link_catalog.links if link.found_in == "Provided"]

    return LinearTicketContent(
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria,
        test_scenarios_summary=test_scenarios_summary,
        source_documentation=source_docs,
    )


def save_json_test_cases(state: ResearchState) -> str:
    """Save JSON test cases to ticket_content subdirectory."""
    from pathlib import Path

    filename = f"{state.white_label}_{state.program_name}_test_cases.json"

    # Use ticket_content subdirectory within the timestamped output directory
    if state.output_dir:
        ticket_dir = Path(state.output_dir) / "ticket_content"
        ticket_dir.mkdir(parents=True, exist_ok=True)
        file_path = ticket_dir / filename
    else:
        file_path = get_output_path(filename)

    json_data = [tc.model_dump() for tc in state.json_test_cases]

    with open(file_path, "w") as f:
        json.dump(json_data, indent=2, fp=f)

    return str(file_path)


def save_program_config(state: ResearchState) -> str:
    """Save program configuration to ticket_content subdirectory."""
    from pathlib import Path

    filename = f"{state.white_label}_{state.program_name}_initial_config.json"

    # Use ticket_content subdirectory within the timestamped output directory
    if state.output_dir:
        ticket_dir = Path(state.output_dir) / "ticket_content"
        ticket_dir.mkdir(parents=True, exist_ok=True)
        file_path = ticket_dir / filename
    else:
        file_path = get_output_path(filename)

    # Convert Pydantic model to dict
    config_dict = state.program_config.model_dump()

    with open(file_path, "w") as f:
        json.dump(config_dict, indent=2, fp=f)

    return str(file_path)


def save_ticket_content_locally(content: LinearTicketContent, state: ResearchState) -> str:
    """Save ticket content to a local markdown file in ticket_content subdirectory."""
    from pathlib import Path

    filename = f"{state.white_label}_{state.program_name}_ticket.md"

    # Use ticket_content subdirectory within the timestamped output directory
    if state.output_dir:
        ticket_dir = Path(state.output_dir) / "ticket_content"
        ticket_dir.mkdir(parents=True, exist_ok=True)
        file_path = ticket_dir / filename
    else:
        file_path = get_output_path(filename)

    lines = [
        f"# {content.title}",
        "",
        content.description,
        "",
        "## Acceptance Criteria",
        "",
    ]

    for criteria in content.acceptance_criteria:
        lines.append(criteria)

    lines.extend([
        "",
        content.test_scenarios_summary,
        "",
        "## Source Documentation",
        "",
    ])

    for url in content.source_documentation:
        lines.append(f"- {url}")

    if content.json_test_file_path:
        lines.extend([
            "",
            "## JSON Test Cases",
            f"File: `{content.json_test_file_path}`",
        ])

    if content.program_config_file_path:
        lines.extend([
            "",
            "## Program Configuration",
            f"File: `{content.program_config_file_path}`",
        ])

    with open(file_path, "w") as f:
        f.write("\n".join(lines))

    return str(file_path)


async def create_linear_issue(content: LinearTicketContent) -> tuple[str, str]:
    """Create an issue in Linear via the API."""

    # Build the full description with acceptance criteria
    full_description = content.description + "\n\n## Acceptance Criteria\n\n"
    for criteria in content.acceptance_criteria:
        full_description += criteria + "\n"

    full_description += "\n" + content.test_scenarios_summary

    # Linear GraphQL mutation
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                id
                url
            }
        }
    }
    """

    variables = {
        "input": {
            "title": content.title,
            "description": full_description,
            "teamId": settings.linear_team_id,
        }
    }

    if settings.linear_project_id:
        variables["input"]["projectId"] = settings.linear_project_id

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": settings.linear_api_key,
                "Content-Type": "application/json",
            },
            json={
                "query": mutation,
                "variables": variables,
            },
        )

        response.raise_for_status()
        data = response.json()

        if data.get("errors"):
            raise Exception(f"Linear API error: {data['errors']}")

        issue_data = data["data"]["issueCreate"]["issue"]
        return issue_data["url"], issue_data["id"]
