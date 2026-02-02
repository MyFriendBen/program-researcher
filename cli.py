"""
CLI entry point for the Program Research Agent.

Usage:
    research-program --program "CSFP" --state "il" --white-label "il" \
        --source-url "https://www.fns.usda.gov/csfp" \
        --source-url "https://www.dhs.state.il.us/page.aspx?item=30513"
"""

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import get_output_path, settings, validate_settings
from .graph import app, run_research
from .state import ResearchState, WorkflowStatus

console = Console()


@click.command()
@click.option(
    "--program",
    required=True,
    help="Program name (e.g., 'CSFP', 'SNAP', 'WIC')",
)
@click.option(
    "--state",
    required=True,
    help="State code (e.g., 'il', 'co', 'nc')",
)
@click.option(
    "--white-label",
    required=True,
    help="White label identifier (e.g., 'il', 'co', 'nc')",
)
@click.option(
    "--source-url",
    multiple=True,
    required=True,
    help="Source documentation URL (can specify multiple)",
)
@click.option(
    "--max-iterations",
    default=3,
    help="Maximum QA loop iterations (default: 3)",
)
@click.option(
    "--output-dir",
    default=None,
    help="Output directory for generated files",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show detailed progress messages",
)
@click.option(
    "--no-save",
    is_flag=True,
    help="Don't save step outputs to files",
)
def research_program(
    program: str,
    state: str,
    white_label: str,
    source_url: tuple,
    max_iterations: int,
    output_dir: str | None,
    dry_run: bool,
    verbose: bool,
    no_save: bool,
):
    """
    Research a benefit program and generate test cases.

    This tool:
    1. Gathers documentation from provided source URLs
    2. Extracts eligibility criteria
    3. Maps criteria to screener fields
    4. Generates test scenarios
    5. Converts to JSON test format
    6. Creates a Linear ticket with acceptance criteria
    """
    # Validate settings (skip API key check for dry-run)
    if not dry_run:
        errors = validate_settings()
        if errors:
            console.print("[red]Configuration errors:[/red]")
            for error in errors:
                console.print(f"  - {error}")
            sys.exit(1)

    # Override output directory if specified
    if output_dir:
        settings.output_dir = Path(output_dir)

    # Show configuration
    console.print(Panel.fit(
        f"[bold]Program Research Agent[/bold]\n\n"
        f"Program: {program}\n"
        f"State: {state.upper()}\n"
        f"White Label: {white_label}\n"
        f"Source URLs: {len(source_url)}\n"
        f"Max QA Iterations: {max_iterations}",
        title="Configuration",
    ))

    if verbose:
        console.print("\n[dim]Source URLs:[/dim]")
        for url in source_url:
            console.print(f"  - {url}")

    if dry_run:
        console.print("\n[yellow]Dry run mode - no actions will be taken[/yellow]")
        show_workflow_preview()
        return

    # Run the workflow
    console.print("\n[bold]Starting research workflow...[/bold]\n")

    try:
        final_state = asyncio.run(
            run_research(
                program_name=program,
                state_code=state,
                white_label=white_label,
                source_urls=list(source_url),
                max_iterations=max_iterations,
                save_outputs=not no_save,
            )
        )

        # Show results
        show_results(final_state)

    except KeyboardInterrupt:
        console.print("\n[yellow]Workflow cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def show_workflow_preview():
    """Show a preview of the workflow steps."""
    console.print("\n[bold]Workflow Steps:[/bold]\n")

    steps = [
        ("1. Gather Links", "Fetch source URLs and extract documentation links"),
        ("2. Read Screener Fields", "Parse Django models for available fields"),
        ("3. Extract Criteria", "Extract eligibility criteria from documentation"),
        ("4. QA Validate Research", "Adversarial review of extracted criteria"),
        ("5. Generate Test Cases", "Create 10-15 human-readable test scenarios"),
        ("6. QA Validate Tests", "Review test coverage and accuracy"),
        ("7. Convert to JSON", "Transform tests to pre_validation_schema format"),
        ("8. QA Validate JSON", "Verify JSON matches source test cases"),
        ("9. Create Linear Ticket", "Generate ticket with acceptance criteria"),
    ]

    table = Table(show_header=True, header_style="bold")
    table.add_column("Step")
    table.add_column("Description")

    for step, desc in steps:
        table.add_row(step, desc)

    console.print(table)


def show_results(state: ResearchState):
    """Display the results of the workflow."""
    console.print("\n" + "=" * 60)
    console.print("[bold green]Workflow Complete![/bold green]")
    console.print("=" * 60 + "\n")

    # Summary table
    table = Table(title="Results Summary", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    # Links discovered
    if state.link_catalog:
        table.add_row("Links Discovered", str(len(state.link_catalog.links)))

    # Criteria
    if state.field_mapping:
        table.add_row(
            "Evaluable Criteria",
            str(len(state.field_mapping.criteria_can_evaluate)),
        )
        table.add_row(
            "Data Gaps",
            str(len(state.field_mapping.criteria_cannot_evaluate)),
        )

    # Test cases
    if state.test_suite:
        table.add_row("Test Scenarios", str(len(state.test_suite.test_cases)))

    # JSON test cases
    table.add_row("JSON Test Cases", str(len(state.json_test_cases)))

    # QA iterations
    table.add_row("Research QA Iterations", str(state.research_iteration))
    table.add_row("Test Case QA Iterations", str(state.test_case_iteration))
    table.add_row("JSON QA Iterations", str(state.json_iteration))

    # Status - handle both enum and string (use_enum_values=True converts to string)
    status_value = state.status.value if hasattr(state.status, 'value') else state.status
    status_color = "green" if status_value == "completed" else "yellow"
    table.add_row("Final Status", f"[{status_color}]{status_value}[/{status_color}]")

    console.print(table)

    # Linear ticket
    if state.linear_ticket_url:
        console.print(f"\n[bold]Linear Ticket:[/bold] {state.linear_ticket_url}")
    elif state.linear_ticket:
        console.print(f"\n[bold]Ticket saved locally[/bold]")

    # Output files
    console.print("\n[bold]Output Files:[/bold]")
    if state.output_dir:
        from pathlib import Path
        output_path = Path(state.output_dir)
        if output_path.exists():
            console.print(f"  Directory: {output_path}")
            for f in sorted(output_path.glob("*")):
                console.print(f"    - {f.name}")
    else:
        output_dir = settings.output_dir
        if output_dir.exists():
            for f in output_dir.glob(f"{state.white_label}_{state.program_name}*"):
                console.print(f"  - {f}")

    # Show messages if verbose
    if state.messages:
        console.print("\n[dim]Workflow Log (last 10 messages):[/dim]")
        for msg in state.messages[-10:]:
            console.print(f"  {msg}")


@click.command()
def show_graph():
    """Display the workflow graph structure."""
    from .graph import get_graph_visualization

    console.print("[bold]Workflow Graph (Mermaid format):[/bold]\n")
    console.print(get_graph_visualization())


@click.group()
def cli():
    """Program Research Agent - AI-powered benefit program research and QA."""
    pass


cli.add_command(research_program, name="research")
cli.add_command(show_graph, name="graph")


if __name__ == "__main__":
    cli()
