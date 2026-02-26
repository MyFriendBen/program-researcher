"""
Utility for saving intermediate outputs from workflow steps.

Saves each step's output to timestamped files for debugging and auditing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import settings


def get_research_output_dir(white_label: str, program_name: str) -> Path:
    """
    Get the output directory for a specific research run.

    Creates a timestamped directory structure:
    output/{white_label}_{program_name}_{timestamp}/
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = settings.output_dir / f"{white_label}_{program_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def save_fetched_content(
    output_dir: Path,
    url: str,
    content: str,
    index: int,
) -> Path:
    """
    Save fetched content to a file in the fetched/ subdirectory.

    Args:
        output_dir: The research output directory
        url: The source URL (used to generate filename)
        content: The fetched content (HTML, JSON string with vision data, or error message)
        index: Index of this source in the source_urls list

    Returns:
        Path to the saved file
    """
    # Create fetched subdirectory
    fetched_dir = output_dir / "fetched"
    fetched_dir.mkdir(exist_ok=True)

    # Sanitize URL for filename (take last part of path, remove special chars)
    url_parts = url.rstrip('/').split('/')
    url_suffix = url_parts[-1] if url_parts else 'source'
    # Remove query params and special chars
    url_suffix = url_suffix.split('?')[0].split('#')[0]
    url_suffix = ''.join(c if c.isalnum() or c in '.-_' else '_' for c in url_suffix)
    # Limit length
    url_suffix = url_suffix[:100]

    # Determine file extension based on content
    from ..tools.vision_helper import is_pdf_vision_content

    if is_pdf_vision_content(content):
        # Vision data - save as JSON
        ext = "pdf.json"
    elif content.startswith("[PDF Document"):
        # PDF that failed vision - save as text log
        ext = "pdf.txt"
    elif "<html" in content.lower() or "<!doctype" in content.lower():
        # HTML content
        ext = "html"
    else:
        # Default to text
        ext = "txt"

    # Build filename: {index}_{sanitized_url}.{ext}
    filename = f"{index}_{url_suffix}.{ext}"
    filepath = fetched_dir / filename

    # Save content
    filepath.write_text(content, encoding='utf-8')

    # Also save a metadata file with URL and fetch info
    metadata = {
        "url": url,
        "index": index,
        "fetched_at": datetime.now().isoformat(),
        "content_size_bytes": len(content),
        "filepath": str(filepath),
    }
    metadata_path = fetched_dir / f"{index}_{url_suffix}.metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    return filepath


def save_step_output(
    output_dir: Path,
    step_name: str,
    data: Any,
    iteration: int | None = None,
) -> Path:
    """
    Save output from a workflow step.

    Args:
        output_dir: Directory to save to
        step_name: Name of the step (e.g., "gather_links", "qa_research")
        data: Data to save (Pydantic model, dict, list, or string)
        iteration: Optional iteration number for QA loops

    Returns:
        Path to the saved file
    """
    # Build filename
    if iteration is not None:
        filename = f"{step_name}_iter{iteration}.json"
    else:
        filename = f"{step_name}.json"

    filepath = output_dir / filename

    # Convert data to serializable format
    if isinstance(data, BaseModel):
        json_data = data.model_dump(mode="json")
    elif isinstance(data, list) and data and isinstance(data[0], BaseModel):
        json_data = [item.model_dump(mode="json") for item in data]
    elif isinstance(data, str):
        # Save as text file instead
        filepath = filepath.with_suffix(".txt")
        filepath.write_text(data)
        return filepath
    else:
        json_data = data

    # Save with pretty formatting
    with open(filepath, "w") as f:
        json.dump(json_data, f, indent=2, default=str)

    return filepath


def save_messages_log(output_dir: Path, messages: list[str]) -> Path:
    """Save the workflow messages log."""
    filepath = output_dir / "workflow_log.txt"

    with open(filepath, "w") as f:
        for i, msg in enumerate(messages, 1):
            f.write(f"[{i:03d}] {msg}\n")

    return filepath


def save_final_summary(
    output_dir: Path,
    state: Any,
) -> Path:
    """
    Save a final summary of the research run.

    Creates a markdown summary with key metrics and file references.
    """
    filepath = output_dir / "SUMMARY.md"

    # Helper to safely get enum values
    def get_value(val):
        return val.value if hasattr(val, 'value') else val

    status = get_value(state.status)
    status_emoji = "✅" if status == "completed" else "❌" if status == "failed" else "⚠️"

    lines = [
        f"# Research Summary: {state.program_name} ({state.state_code.upper()})",
        "",
        f"**White Label:** {state.white_label}",
        f"**Research Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Status:** {status_emoji} {status.upper()}",
        "",
    ]

    # If failed, show error and next steps prominently
    if status == "failed":
        lines.extend([
            "## ❌ Workflow Failed",
            "",
        ])

        if state.error_message:
            lines.extend([
                "### Error",
                f"```",
                state.error_message,
                f"```",
                "",
            ])

        # Extract recent error messages from workflow log
        error_messages = [msg for msg in state.messages if any(
            keyword in msg.lower() for keyword in ["error", "failed", "critical failure", "cannot"]
        )]
        if error_messages:
            lines.extend([
                "### Error Details from Log",
                "",
            ])
            for msg in error_messages[-5:]:  # Last 5 error-related messages
                lines.append(f"- {msg}")
            lines.append("")

        # Determine next steps based on what failed
        lines.extend([
            "### Next Steps",
            "",
        ])

        if not state.test_suite or (hasattr(state.test_suite, 'test_cases') and not state.test_suite.test_cases):
            lines.extend([
                "1. **Test case generation failed** - The LLM response could not be parsed",
                "   - This often happens when the response is too long and gets truncated",
                "   - Try running again - LLM responses can vary",
                "   - Consider breaking down the request or using a different approach",
                "",
            ])
        elif not state.json_test_cases:
            lines.extend([
                "1. **JSON conversion failed** - Test cases couldn't be converted to JSON format",
                "   - Check the test case data for missing required fields",
                "   - Review the schema validation errors in the log",
                "",
            ])
        elif not state.field_mapping:
            lines.extend([
                "1. **Criteria extraction failed** - Could not extract eligibility criteria",
                "   - Check if source URLs are accessible",
                "   - Verify the documentation contains eligibility information",
                "",
            ])

        lines.extend([
            "To retry: Run the same command again",
            "",
            "---",
            "",
        ])

    lines.extend([
        "## Source URLs",
        "",
    ])

    for url in state.source_urls:
        lines.append(f"- {url}")

    lines.extend(["", "## Results Summary", ""])

    # Links discovered
    if state.link_catalog:
        lines.append(f"**Links Discovered:** {len(state.link_catalog.links)}")

        # Category breakdown
        categories = {}
        for link in state.link_catalog.links:
            cat = get_value(link.category)
            categories[cat] = categories.get(cat, 0) + 1

        for cat, count in sorted(categories.items()):
            lines.append(f"  - {cat}: {count}")
        lines.append("")

    # Criteria
    if state.field_mapping:
        lines.append(f"**Evaluable Criteria:** {len(state.field_mapping.criteria_can_evaluate)}")
        lines.append(f"**Data Gaps:** {len(state.field_mapping.criteria_cannot_evaluate)}")
        lines.append("")

    # Test cases
    if state.test_suite:
        lines.append(f"**Test Scenarios:** {len(state.test_suite.test_cases)}")

        # Category breakdown
        categories = {}
        for tc in state.test_suite.test_cases:
            categories[tc.category] = categories.get(tc.category, 0) + 1

        for cat, count in sorted(categories.items()):
            lines.append(f"  - {cat}: {count}")
        lines.append("")

    # JSON test cases
    lines.append(f"**JSON Test Cases:** {len(state.json_test_cases)}")
    lines.append("")

    # QA iterations
    lines.extend([
        "## QA Iterations",
        "",
        f"- Research QA: {state.research_iteration}",
        f"- Test Case QA: {state.test_case_iteration}",
        f"- JSON QA: {state.json_iteration}",
        "",
    ])

    # Linear ticket
    if state.linear_ticket_url:
        lines.extend([
            "## Linear Ticket",
            "",
            f"**URL:** {state.linear_ticket_url}",
            "",
        ])
    elif state.linear_ticket:
        lines.extend([
            "## Linear Ticket",
            "",
            "Ticket content generated (see `linear_ticket.json`)",
            "",
        ])

    # Output files
    lines.extend([
        "## Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
    ])

    # List all files in the output directory
    for f in sorted(output_dir.glob("*")):
        if f.name != "SUMMARY.md":
            if f.is_dir():
                # Count files in subdirectory
                file_count = len(list(f.glob("*")))
                lines.append(f"| `{f.name}/` | Directory with {file_count} files |")
            else:
                desc = _get_file_description(f.name)
                lines.append(f"| `{f.name}` | {desc} |")

    lines.append("")

    # Add last workflow messages for context
    if state.messages:
        lines.extend([
            "## Workflow Log (Last 15 Messages)",
            "",
        ])
        for msg in state.messages[-15:]:
            # Escape any markdown characters and format as list
            escaped_msg = msg.replace("|", "\\|").replace("`", "\\`")
            lines.append(f"- {escaped_msg}")
        lines.append("")

    filepath.write_text("\n".join(lines))
    return filepath


def _get_file_description(filename: str) -> str:
    """Get a description for an output file."""
    descriptions = {
        "gather_links.json": "Discovered documentation links",
        "screener_fields.json": "Available screener fields from Django models",
        "extract_criteria.json": "Extracted eligibility criteria and field mapping",
        "generate_tests.json": "Human-readable test scenarios",
        "convert_json.json": "JSON test cases for pre-validation",
        "linear_ticket.json": "Linear ticket content",
        "workflow_log.txt": "Full workflow execution log",
    }

    # Check for exact match
    if filename in descriptions:
        return descriptions[filename]

    # Check for QA iteration files
    if filename.startswith("qa_research"):
        return "QA validation of research"
    if filename.startswith("qa_tests"):
        return "QA validation of test cases"
    if filename.startswith("qa_json"):
        return "QA validation of JSON output"
    if filename.startswith("fix_"):
        return "Fixes applied based on QA feedback"

    return "Research output"
