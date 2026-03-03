"""Tests for generate_tests node."""

import asyncio

import pytest

from program_research_agent.state import (
    HumanTestCase,
    IssueSeverity,
    QAIssue,
    QAValidationResult,
    ResearchState,
    ScenarioStep,
    ScenarioSuite,
)


def _make_state(**kwargs) -> ResearchState:
    defaults = dict(
        program_name="CSFP",
        state_code="il",
        white_label="il",
        source_urls=["https://example.com"],
    )
    defaults.update(kwargs)
    return ResearchState(**defaults)


def _make_test_suite() -> ScenarioSuite:
    tc = HumanTestCase(
        scenario_number=1,
        title="Eligible Senior",
        what_checking="Typical eligible senior",
        category="happy_path",
        expected_eligible=True,
        steps=[ScenarioStep(section="Location", instructions=["Enter ZIP 60601"])],
        what_to_look_for=["CSFP appears"],
        why_matters="Baseline test",
        zip_code="60601",
        county="Cook",
        household_size=1,
        household_assets=0,
        members_data=[
            {
                "relationship": "headOfHousehold",
                "birth_month": 3,
                "birth_year": 1953,
                "income_streams": [{"type": "sSRetirement", "amount": 800, "frequency": "monthly"}],
                "insurance": {"none": True},
            }
        ],
    )
    return ScenarioSuite(program_name="CSFP", white_label="il", test_cases=[tc])


def _make_qa_result_with_issues() -> QAValidationResult:
    return QAValidationResult(
        validation_type="test_cases",
        overall_status="NEEDS_REVISION",
        issues=[
            QAIssue(
                severity=IssueSeverity.MAJOR,
                issue_type="missing_test",
                description="No test for ineligible household above income limit",
                location="test_cases",
                suggested_fix="Add a test case with income above 130% FPL",
            )
        ],
        summary="1 major issue found",
        recommendation="Revise",
    )


def run_async(coro):
    """Run an async coroutine synchronously for tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFixTestCasesNodeEarlyExit:
    """Tests for fix_test_cases_node() early-exit conditions (no LLM call)."""

    def test_no_qa_result_returns_messages(self):
        """When test_case_qa_result is None, node returns without calling LLM."""
        from program_research_agent.nodes.generate_tests import fix_test_cases_node

        state = _make_state(test_suite=_make_test_suite())
        result = run_async(fix_test_cases_node(state))

        assert "messages" in result
        assert any("No issues to fix" in m for m in result["messages"])
        assert "test_suite" not in result

    def test_empty_issues_list_returns_messages(self):
        """When test_case_qa_result has no issues, node returns without calling LLM."""
        from program_research_agent.nodes.generate_tests import fix_test_cases_node

        qa_result = QAValidationResult(
            validation_type="test_cases",
            overall_status="VALIDATED",
            issues=[],
            summary="All good",
            recommendation="Proceed",
        )
        state = _make_state(test_suite=_make_test_suite(), test_case_qa_result=qa_result)
        result = run_async(fix_test_cases_node(state))

        assert "messages" in result
        assert any("No issues to fix" in m for m in result["messages"])
        assert "test_suite" not in result

    def test_no_test_suite_returns_messages(self):
        """When test_suite is None, node returns without calling LLM."""
        from program_research_agent.nodes.generate_tests import fix_test_cases_node

        state = _make_state(test_case_qa_result=_make_qa_result_with_issues())
        result = run_async(fix_test_cases_node(state))

        assert "messages" in result
        assert any("No test suite to fix" in m for m in result["messages"])
        assert "test_suite" not in result

    def test_preserves_existing_messages(self):
        """Existing state messages are preserved in the output."""
        from program_research_agent.nodes.generate_tests import fix_test_cases_node

        state = _make_state(
            test_suite=_make_test_suite(),
            messages=["Previous message"],
        )
        result = run_async(fix_test_cases_node(state))

        assert "Previous message" in result["messages"]
