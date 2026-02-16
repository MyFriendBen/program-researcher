"""
Main LangGraph definition for the Program Research Agent.

This module defines the workflow graph that orchestrates:
1. Link gathering and documentation research
2. Eligibility criteria extraction and field mapping
3. QA validation loops
4. Test case generation
5. JSON conversion
6. Linear ticket creation
"""

from pathlib import Path
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes.convert_json import convert_to_json_node, fix_json_node
from .nodes.extract_criteria import extract_criteria_node
from .nodes.gather_links import gather_links_node
from .nodes.generate_program_config import generate_program_config_node
from .nodes.generate_tests import fix_test_cases_node, generate_tests_node
from .nodes.linear_ticket import create_linear_ticket_node
from .nodes.qa_json import qa_validate_json_node
from .nodes.qa_research import fix_research_node, qa_validate_research_node
from .nodes.qa_tests import qa_validate_tests_node
from .nodes.read_screener_fields import read_screener_fields_node
from .state import ResearchState, WorkflowStatus
from .tools.output_saver import (
    get_research_output_dir,
    save_final_summary,
    save_messages_log,
    save_step_output,
)


# -----------------------------------------------------------------------------
# Conditional Edge Functions
# -----------------------------------------------------------------------------


def should_fix_research(state: ResearchState) -> Literal["fix_research", "generate_tests"]:
    """
    Determine whether to fix research issues or proceed to test generation.

    Returns 'fix_research' if there are unresolved issues and we haven't
    exceeded max iterations. Otherwise returns 'generate_tests'.
    """
    if not state.research_qa_result:
        return "generate_tests"

    # Check if there are critical or major issues
    # Handle both enum and string (use_enum_values=True converts to string)
    def get_severity(issue):
        return issue.severity.value if hasattr(issue.severity, 'value') else issue.severity

    has_blocking_issues = any(
        get_severity(issue) in ("critical", "major") and not issue.resolved
        for issue in state.research_qa_result.issues
    )

    # Check iteration limit
    within_limit = state.research_iteration < state.max_iterations

    if has_blocking_issues and within_limit:
        return "fix_research"

    return "generate_tests"


def should_fix_tests(state: ResearchState) -> Literal["fix_test_cases", "convert_json"]:
    """
    Determine whether to fix test case issues or proceed to JSON conversion.
    """
    if not state.test_case_qa_result:
        return "convert_json"

    # Handle both enum and string (use_enum_values=True converts to string)
    def get_severity(issue):
        return issue.severity.value if hasattr(issue.severity, 'value') else issue.severity

    has_blocking_issues = any(
        get_severity(issue) in ("critical", "major") and not issue.resolved
        for issue in state.test_case_qa_result.issues
    )

    within_limit = state.test_case_iteration < state.max_iterations

    if has_blocking_issues and within_limit:
        return "fix_test_cases"

    return "convert_json"


def should_fix_json(state: ResearchState) -> Literal["fix_json", "create_ticket"]:
    """
    Determine whether to fix JSON issues or proceed to ticket creation.
    """
    if not state.json_qa_result:
        return "create_ticket"

    # Handle both enum and string (use_enum_values=True converts to string)
    def get_severity(issue):
        return issue.severity.value if hasattr(issue.severity, 'value') else issue.severity

    has_blocking_issues = any(
        get_severity(issue) in ("critical", "major") and not issue.resolved
        for issue in state.json_qa_result.issues
    )

    within_limit = state.json_iteration < state.max_iterations

    if has_blocking_issues and within_limit:
        return "fix_json"

    return "create_ticket"


def _get_status(state: ResearchState) -> str:
    """Helper to get status as string."""
    return state.status.value if hasattr(state.status, 'value') else state.status


def check_after_generate_tests(state: ResearchState) -> Literal["qa_validate_tests", "end"]:
    """
    Check if test generation succeeded before proceeding to QA.
    """
    if _get_status(state) == "failed":
        return "end"
    if not state.test_suite or not state.test_suite.test_cases:
        return "end"
    return "qa_validate_tests"


def check_after_convert_json(state: ResearchState) -> Literal["qa_validate_json", "end"]:
    """
    Check if JSON conversion succeeded before proceeding to QA.
    """
    if _get_status(state) == "failed":
        return "end"
    if not state.json_test_cases:
        return "end"
    return "qa_validate_json"


# -----------------------------------------------------------------------------
# Graph Definition
# -----------------------------------------------------------------------------


def create_research_graph() -> StateGraph:
    """
    Create the LangGraph workflow for program research.

    The graph follows this flow:
    1. gather_links -> read_screener_fields -> extract_criteria
    2. qa_validate_research -> [fix_research loop] -> generate_tests
    3. qa_validate_tests -> [fix_test_cases loop] -> convert_json
    4. qa_validate_json -> [fix_json loop] -> create_ticket
    5. END
    """
    # Create the graph with our state type
    workflow = StateGraph(ResearchState)

    # Add all nodes
    workflow.add_node("gather_links", gather_links_node)
    workflow.add_node("read_screener_fields", read_screener_fields_node)
    workflow.add_node("extract_criteria", extract_criteria_node)
    workflow.add_node("qa_validate_research", qa_validate_research_node)
    workflow.add_node("fix_research", fix_research_node)
    workflow.add_node("generate_tests", generate_tests_node)
    workflow.add_node("qa_validate_tests", qa_validate_tests_node)
    workflow.add_node("fix_test_cases", fix_test_cases_node)
    workflow.add_node("convert_json", convert_to_json_node)
    workflow.add_node("qa_validate_json", qa_validate_json_node)
    workflow.add_node("fix_json", fix_json_node)
    workflow.add_node("generate_program_config", generate_program_config_node)
    workflow.add_node("create_ticket", create_linear_ticket_node)

    # Define the flow
    # Entry point
    workflow.set_entry_point("gather_links")

    # Linear flow for research phase
    workflow.add_edge("gather_links", "read_screener_fields")
    workflow.add_edge("read_screener_fields", "extract_criteria")
    workflow.add_edge("extract_criteria", "qa_validate_research")

    # Research QA loop
    workflow.add_conditional_edges(
        "qa_validate_research",
        should_fix_research,
        {
            "fix_research": "fix_research",
            "generate_tests": "generate_tests",
        },
    )
    workflow.add_edge("fix_research", "qa_validate_research")  # Loop back

    # Test case generation - check for failure before QA
    workflow.add_conditional_edges(
        "generate_tests",
        check_after_generate_tests,
        {
            "qa_validate_tests": "qa_validate_tests",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "qa_validate_tests",
        should_fix_tests,
        {
            "fix_test_cases": "fix_test_cases",
            "convert_json": "convert_json",
        },
    )
    workflow.add_edge("fix_test_cases", "qa_validate_tests")  # Loop back

    # JSON conversion - check for failure before QA
    workflow.add_conditional_edges(
        "convert_json",
        check_after_convert_json,
        {
            "qa_validate_json": "qa_validate_json",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "qa_validate_json",
        should_fix_json,
        {
            "fix_json": "fix_json",
            "create_ticket": "generate_program_config",  # Changed: go to config generation first
        },
    )
    workflow.add_edge("fix_json", "qa_validate_json")  # Loop back

    # Program config generation, then ticket creation
    workflow.add_edge("generate_program_config", "create_ticket")

    # Final step
    workflow.add_edge("create_ticket", END)

    return workflow


def compile_graph(checkpointer=None):
    """
    Compile the graph with optional checkpointing.

    Args:
        checkpointer: Optional checkpointer for state persistence.
                     If None, uses in-memory checkpointing.

    Returns:
        Compiled LangGraph application
    """
    workflow = create_research_graph()

    if checkpointer is None:
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


# Create a default compiled graph instance
app = compile_graph()


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


async def run_research(
    program_name: str,
    state_code: str,
    white_label: str,
    source_urls: list[str],
    max_iterations: int = 3,
    thread_id: str | None = None,
    save_outputs: bool = True,
) -> ResearchState:
    """
    Run the full research workflow for a program.

    Args:
        program_name: Name of the benefit program
        state_code: State code (e.g., 'il', 'co')
        white_label: White label identifier
        source_urls: List of source documentation URLs
        max_iterations: Maximum QA loop iterations
        thread_id: Optional thread ID for checkpointing
        save_outputs: Whether to save step outputs to files

    Returns:
        Final ResearchState with all outputs
    """
    # Create output directory if saving outputs
    output_dir = None
    if save_outputs:
        output_dir = get_research_output_dir(white_label, program_name)
        print(f"[setup] Output directory: {output_dir}")

    # Initialize state
    initial_state = ResearchState(
        program_name=program_name,
        state_code=state_code,
        white_label=white_label,
        source_urls=source_urls,
        max_iterations=max_iterations,
        messages=[f"Starting research for {program_name} ({state_code})..."],
        output_dir=str(output_dir) if output_dir else None,
    )

    # Configure thread
    config = {
        "configurable": {
            "thread_id": thread_id or f"{white_label}_{program_name}",
        }
    }

    # Run the graph
    final_state = None
    printed_message_count = len(initial_state.messages)
    error_occurred = None

    try:
        async for event in app.astream(initial_state, config):
            # Each event is a dict with the node name as key
            for node_name, node_output in event.items():
                if "messages" in node_output:
                    # Only print NEW messages (skip already printed ones)
                    all_messages = node_output["messages"]
                    new_messages = all_messages[printed_message_count:]
                    for msg in new_messages:
                        print(f"[{node_name}] {msg}")
                    printed_message_count = len(all_messages)

                # Save step output if enabled
                if save_outputs and output_dir:
                    _save_node_output(output_dir, node_name, node_output)

            # Update final state
            final_state = app.get_state(config).values

    except Exception as e:
        error_occurred = e
        print(f"[error] Workflow failed: {e}")
        # Try to get whatever state we have
        try:
            final_state = app.get_state(config).values
        except Exception:
            pass

    # Build final state object
    result_state = ResearchState(**final_state) if final_state else initial_state

    # If there was an error, update the state to reflect it
    if error_occurred:
        result_state.status = WorkflowStatus.FAILED
        result_state.error_message = str(error_occurred)
        result_state.messages.append(f"Workflow failed with error: {error_occurred}")

    # Always save final summary and messages log (even on error)
    if save_outputs and output_dir:
        save_messages_log(output_dir, result_state.messages)
        save_final_summary(output_dir, result_state)
        print(f"[complete] Outputs saved to: {output_dir}")

    # Re-raise the error after saving
    if error_occurred:
        raise error_occurred

    return result_state


def _save_node_output(output_dir: Path | str, node_name: str, node_output: dict) -> None:
    """Save the output from a node to files."""
    output_dir = Path(output_dir)

    # Map node names to their key outputs
    output_mapping = {
        "gather_links": ("link_catalog", None),
        "read_screener_fields": ("screener_fields", None),
        "extract_criteria": ("field_mapping", None),
        "qa_validate_research": ("research_qa_result", "research_iteration"),
        "fix_research": (None, None),  # No primary output
        "generate_tests": ("test_suite", None),
        "qa_validate_tests": ("test_case_qa_result", "test_case_iteration"),
        "fix_test_cases": (None, None),
        "convert_json": ("json_test_cases", None),
        "qa_validate_json": ("json_qa_result", "json_iteration"),
        "fix_json": (None, None),
        "generate_program_config": ("program_config", None),
        "create_ticket": ("linear_ticket", None),
    }

    if node_name not in output_mapping:
        return

    output_key, iteration_key = output_mapping[node_name]

    if output_key and output_key in node_output:
        data = node_output[output_key]
        iteration = node_output.get(iteration_key) if iteration_key else None

        if data is not None:
            save_step_output(output_dir, node_name, data, iteration)


def get_graph_visualization():
    """
    Get a visualization of the graph structure.

    Returns:
        Mermaid diagram string or description
    """
    try:
        compiled = compile_graph()
        return compiled.get_graph().draw_mermaid()
    except AttributeError:
        # Fallback if draw_mermaid not available
        return """
graph TD
    gather_links --> read_screener_fields
    read_screener_fields --> extract_criteria
    extract_criteria --> qa_validate_research
    qa_validate_research --> |issues| fix_research
    qa_validate_research --> |no issues| generate_tests
    fix_research --> qa_validate_research
    generate_tests --> qa_validate_tests
    qa_validate_tests --> |issues| fix_test_cases
    qa_validate_tests --> |no issues| convert_json
    fix_test_cases --> qa_validate_tests
    convert_json --> qa_validate_json
    qa_validate_json --> |issues| fix_json
    qa_validate_json --> |no issues| create_ticket
    fix_json --> qa_validate_json
    create_ticket --> END
"""
