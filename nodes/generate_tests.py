"""
Node: Generate Test Cases

Step 5 of the QA process - generate human-readable test scenarios.
"""

from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    TIER_VARIANCE,
    HumanTestCase,
    ResearchState,
    ScenarioSuite,
    WorkflowStatus,
)
from ..tools.screener_fields import format_fields_for_prompt


async def generate_tests_node(state: ResearchState) -> dict:
    """
    Generate human-readable test scenarios ONE AT A TIME.

    This approach prevents response truncation by generating each test case
    individually and accumulating the results.
    """
    messages = list(state.messages)
    messages.append(f"Generating test scenarios for {state.program_name}...")

    # Format criteria for prompt
    criteria_text = format_evaluable_criteria(state.field_mapping)

    # Structured output: each call returns a validated HumanTestCase directly.
    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=4096,  # Smaller max tokens for single test cases
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    ).with_structured_output(HumanTestCase)

    # Get test case categories
    categories = RESEARCHER_PROMPTS.get("test_case_categories", [])
    if not categories:
        # Fallback categories
        categories = [
            ("happy_path", "Clearly eligible household"),
            ("happy_path", "Minimally eligible household"),
            ("income_threshold", "Income just below limit"),
            ("income_threshold", "Income just above limit"),
            ("age_threshold", "Age at minimum requirement"),
            ("age_threshold", "Age below minimum"),
            ("exclusion", "Already receives benefit"),
            ("multi_member", "Mixed eligibility household"),
        ]

    # Build the variance directive from the ticket's Tier tag. This shapes whether the
    # scenarios isolate the state-specific value (light spec) or cover all eligibility
    # branches (full spec) — mirroring Decision: Tier on the ticket/spreadsheet.
    variance_directive = build_variance_directive(state)

    test_cases = []
    failed_count = 0

    messages.append(f"Generating {len(categories)} test scenarios one at a time...")

    for i, (category, description) in enumerate(categories, 1):
        # Format previous scenarios for context (just titles to save tokens)
        previous = "\n".join(
            f"- Scenario {tc.scenario_number}: {tc.title} ({tc.category})"
            for tc in test_cases
        ) or "None yet"

        today = date.today()
        prompt = RESEARCHER_PROMPTS["generate_single_test_case"].format(
            program_name=state.program_name,
            state_code=state.state_code,
            white_label=state.white_label,
            criteria_can_evaluate=criteria_text,
            category=category,
            scenario_number=i,
            category_description=description,
            previous_scenarios=previous,
            current_date=today.isoformat(),
            current_year=today.year,
            variance_directive=variance_directive,
        )

        try:
            test_case = await llm.ainvoke(
                [
                    SystemMessage(content=RESEARCHER_PROMPTS["system"]),
                    HumanMessage(content=prompt),
                ]
            )

            # Force the loop-assigned scenario number and category so they stay
            # consistent regardless of what the model echoes back.
            test_case.scenario_number = i
            if not test_case.category:
                test_case.category = category
            test_cases.append(test_case)
            messages.append(f"  [{i}/{len(categories)}] Generated: {test_case.title}")

        except Exception as e:
            # Catch ALL exceptions to prevent one bad test case from stopping everything
            failed_count += 1
            messages.append(f"  [{i}/{len(categories)}] Failed to generate {category} test case: {e}")
            # Continue with other test cases instead of failing completely

    # Check if we have enough test cases
    if len(test_cases) < 3:
        messages.append(f"Only generated {len(test_cases)} test cases - insufficient for QA")
        return {
            "test_suite": None,
            "messages": messages,
            "error_message": f"Only generated {len(test_cases)} of {len(categories)} test cases",
            "status": WorkflowStatus.FAILED,
        }

    # Build test suite
    test_suite = ScenarioSuite(
        program_name=state.program_name,
        white_label=state.white_label,
        test_cases=test_cases,
        coverage_summary=f"Generated {len(test_cases)} scenarios ({failed_count} failed). "
        f"Categories: {', '.join(set(tc.category for tc in test_cases))}",
    )

    # Analyze coverage
    category_counts = {}
    for tc in test_cases:
        category_counts[tc.category] = category_counts.get(tc.category, 0) + 1

    messages.append(f"Generated {len(test_cases)} test scenarios successfully")
    messages.append(f"Coverage by category: {category_counts}")

    return {
        "test_suite": test_suite,
        "messages": messages,
    }


def build_variance_directive(state: ResearchState) -> str:
    """
    Build a scenario-coverage directive from the ticket's Tier tag.

    Maps Decision: Tier -> what varies for our state (the Δ) -> how to shape scenarios:
      - value  : light spec. Eligibility is federal/trusted; scenarios should ISOLATE the
                 state-specific benefit value so a drift in that value breaks a scenario.
      - elig   : full spec. Eligibility varies, so cover EVERY eligibility branch
                 (eligible + ineligible per criterion, boundaries, multi-member) AND pin values.
      - none   : config-only tier (no spec normally produced).
    """
    # state.tier may be an enum or a plain string (use_enum_values=True stores the value)
    tier = None
    if state.tier:
        tier = state.tier.value if hasattr(state.tier, "value") else state.tier
    variance = TIER_VARIANCE.get(tier) if tier else None

    if variance == "value":
        return (
            "### Scenario focus (Tier = value varies → LIGHT spec)\n"
            "Eligibility for this program is federal and trusted — do NOT exhaustively re-test "
            "eligibility branches. Instead, build scenarios that ISOLATE the state-specific "
            "benefit VALUE: each eligible scenario must pin a committed numeric `expected_amount`, "
            "and the set should be chosen so that an incorrect/stale state value would make a "
            "scenario fail. Include at least one clearly-ineligible scenario for sanity, but keep "
            "eligibility variation minimal."
        )
    if variance == "elig":
        return (
            "### Scenario focus (Tier = eligibility varies → FULL spec)\n"
            "Eligibility varies for our state, so eligibility cannot be trusted. Cover EVERY major "
            "eligibility branch: at least one clearly-eligible and one clearly-ineligible case per "
            "major criterion, boundary/threshold cases, and multi-member interactions. Every "
            "eligible scenario must also pin a committed numeric `expected_amount`."
        )
    if variance == "none":
        return (
            "### Scenario focus (Tier = no variance)\n"
            "This program normally needs no spec (config only). If generating scenarios anyway, "
            "keep them minimal — a clearly-eligible and a clearly-ineligible case — with a "
            "committed numeric `expected_amount` on the eligible one."
        )
    # No tier provided — default to thorough coverage with committed values.
    return (
        "### Scenario focus\n"
        "Cover the major eligibility branches (eligible + ineligible per criterion, boundaries, "
        "multi-member). Every eligible scenario must pin a committed numeric `expected_amount`."
    )


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
    Fix test case issues identified by QA.

    Sends the FULL current test suite (as JSON) plus the QA issues to the
    researcher model, then parses the corrected scenarios back into a
    ScenarioSuite so the next QA pass validates the improved version.

    Token note: the suite is bounded (a handful of scenarios) and the output is
    the same JSON shape the generation step already produces, so this stays
    within model_max_tokens. On any parse failure the original suite is left
    intact and the iteration counter bounds the loop.
    """
    messages = list(state.messages)
    messages.append("Fixing test case issues identified by QA...")

    if not state.test_case_qa_result or not state.test_case_qa_result.issues:
        messages.append("No issues to fix")
        return {"messages": messages}

    if not state.test_suite or not state.test_suite.test_cases:
        messages.append("No test suite available to fix")
        return {"messages": messages}

    from .qa_research import format_qa_issues

    current_output = state.test_suite.model_dump_json(indent=2)
    issues_text = format_qa_issues(state.test_case_qa_result.issues)

    # Structured output: the model returns a corrected ScenarioSuite directly.
    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    ).with_structured_output(ScenarioSuite)

    today = date.today()
    prompt = RESEARCHER_PROMPTS["fix_test_cases"].format(
        program_name=state.program_name,
        state_code=state.state_code,
        current_output=current_output,
        qa_issues=issues_text,
        current_date=today.isoformat(),
        current_year=today.year,
    )

    try:
        revised = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCHER_PROMPTS["system"]),
                HumanMessage(content=prompt),
            ]
        )
        if not revised.test_cases:
            raise ValueError("No test cases in fix response")
    except Exception as e:
        # Leave the suite unchanged; qa_validate_tests will re-flag on the next
        # pass and the iteration counter bounds the loop.
        messages.append(f"Could not parse fix response ({e}); leaving test suite unchanged")
        return {"messages": messages}

    fixed_cases = revised.test_cases
    # Preserve suite identity from state; only the scenarios were revised.
    fixed_suite = ScenarioSuite(
        program_name=state.test_suite.program_name,
        white_label=state.test_suite.white_label,
        test_cases=fixed_cases,
        coverage_summary=f"Revised suite after QA fixes: {len(fixed_cases)} scenarios",
    )

    for issue in state.test_case_qa_result.issues:
        issue.resolved = True

    messages.append(
        f"Applied fixes for {len(state.test_case_qa_result.issues)} issues; "
        f"suite now has {len(fixed_cases)} scenarios"
    )

    return {
        "test_suite": fixed_suite,
        "test_case_qa_result": state.test_case_qa_result,
        "messages": messages,
    }
