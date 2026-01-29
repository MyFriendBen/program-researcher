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

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes.convert_json import convert_to_json_node, fix_json_node
from .nodes.extract_criteria import extract_criteria_node
from .nodes.gather_links import gather_links_node
from .nodes.generate_tests import fix_test_cases_node, generate_tests_node
from .nodes.linear_ticket import create_linear_ticket_node
from .nodes.qa_json import qa_validate_json_node
from .nodes.qa_research import fix_research_node, qa_validate_research_node
from .nodes.qa_tests import qa_validate_tests_node
from .nodes.read_screener_fields import read_screener_fields_node
from .state import ResearchState, WorkflowStatus


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
    has_blocking_issues = any(
        issue.severity.value in ("critical", "major") and not issue.resolved
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

    has_blocking_issues = any(
        issue.severity.value in ("critical", "major") and not issue.resolved
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

    has_blocking_issues = any(
        issue.severity.value in ("critical", "major") and not issue.resolved
        for issue in state.json_qa_result.issues
    )

    within_limit = state.json_iteration < state.max_iterations

    if has_blocking_issues and within_limit:
        return "fix_json"

    return "create_ticket"


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

    # Test case generation and QA loop
    workflow.add_edge("generate_tests", "qa_validate_tests")
    workflow.add_conditional_edges(
        "qa_validate_tests",
        should_fix_tests,
        {
            "fix_test_cases": "fix_test_cases",
            "convert_json": "convert_json",
        },
    )
    workflow.add_edge("fix_test_cases", "qa_validate_tests")  # Loop back

    # JSON conversion and QA loop
    workflow.add_edge("convert_json", "qa_validate_json")
    workflow.add_conditional_edges(
        "qa_validate_json",
        should_fix_json,
        {
            "fix_json": "fix_json",
            "create_ticket": "create_ticket",
        },
    )
    workflow.add_edge("fix_json", "qa_validate_json")  # Loop back

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

    Returns:
        Final ResearchState with all outputs
    """
    # Initialize state
    initial_state = ResearchState(
        program_name=program_name,
        state_code=state_code,
        white_label=white_label,
        source_urls=source_urls,
        max_iterations=max_iterations,
        messages=[f"Starting research for {program_name} ({state_code})..."],
    )

    # Configure thread
    config = {
        "configurable": {
            "thread_id": thread_id or f"{white_label}_{program_name}",
        }
    }

    # Run the graph
    final_state = None
    async for event in app.astream(initial_state, config):
        # Each event is a dict with the node name as key
        for node_name, node_output in event.items():
            if "messages" in node_output:
                for msg in node_output["messages"]:
                    print(f"[{node_name}] {msg}")

        # Update final state
        final_state = app.get_state(config).values

    return ResearchState(**final_state) if final_state else initial_state


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
