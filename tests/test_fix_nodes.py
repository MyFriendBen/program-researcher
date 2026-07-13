"""Tests for the QA fix nodes (fix_research, fix_test_cases, fix_json).

Each node sends the current artifact plus the QA issues to the researcher model
and parses the corrected artifact back into state. The LLM call is stubbed so the
tests exercise the guard / parse / state-update logic deterministically.
"""

import json

import program_research_agent.nodes.convert_json as cj
import program_research_agent.nodes.generate_tests as gt
import program_research_agent.nodes.qa_research as qa
import pytest
from program_research_agent.state import (
    EligibilityCriterion,
    FieldMapping,
    HumanTestCase,
    ImpactLevel,
    IssueSeverity,
    JSONTestCase,
    JSONTestCaseExpectedResults,
    JSONTestCaseHousehold,
    JSONTestCaseMember,
    QAIssue,
    QAValidationResult,
    ResearchState,
    ScenarioStep,
    ScenarioSuite,
)


class _FakeResponse:
    def __init__(self, text):
        self.content = text


class _FakeLLM:
    """Stands in for ChatAnthropic: constructed with any kwargs, returns canned text."""

    def __init__(self, text):
        self._text = text

    def __call__(self, *args, **kwargs):
        return self

    async def ainvoke(self, _messages):
        return _FakeResponse(self._text)


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


def _issue() -> QAIssue:
    return QAIssue(
        severity=IssueSeverity.MAJOR,
        issue_type="wrong_threshold",
        description="threshold is off",
        location="criterion 1",
        suggested_fix="use the correct threshold",
    )


def _qa_result(validation_type: str) -> QAValidationResult:
    return QAValidationResult(
        validation_type=validation_type,
        overall_status="NEEDS_REVISION",
        issues=[_issue()],
        summary="needs work",
        recommendation="revise",
    )


_BASE = {"program_name": "csfp", "state_code": "il", "white_label": "il", "source_urls": ["http://x"]}


def _field_mapping() -> FieldMapping:
    return FieldMapping(
        program_name="csfp",
        criteria_can_evaluate=[
            EligibilityCriterion(
                criterion="age >= 60", source_reference="r", notes="", impact=ImpactLevel.MEDIUM
            )
        ],
        criteria_cannot_evaluate=[],
        summary="old summary",
        recommendations=[],
    )


def _scenario_suite() -> ScenarioSuite:
    tc = HumanTestCase(
        scenario_number=1,
        title="old title",
        what_checking="w",
        category="happy_path",
        expected_eligible=True,
        expected_amount=100,
        steps=[ScenarioStep(section="Location", instructions=["Enter ZIP `60601`"])],
        what_to_look_for=["eligible"],
        why_matters="w",
        zip_code="60601",
        county="Cook",
        household_size=1,
        members_data=[{"relationship": "headOfHousehold"}],
    )
    return ScenarioSuite(program_name="csfp", white_label="il", test_cases=[tc])


def _json_test_case() -> JSONTestCase:
    return JSONTestCase(
        notes="old notes",
        household=JSONTestCaseHousehold(
            white_label="il",
            household_size=1,
            zipcode="60601",
            county="Cook",
            household_members=[
                JSONTestCaseMember(relationship="headOfHousehold", birth_month=3, birth_year=1953, age=72)
            ],
        ),
        expected_results=JSONTestCaseExpectedResults(program_name="il_csfp", eligible=True, value=100),
    )


# ---------------------------------------------------------------------------
# fix_research_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_research_applies_corrections(monkeypatch):
    payload = {
        "criteria_can_evaluate": [
            {
                "criterion": "age >= 60 CORRECTED",
                "source_reference": "7 CFR 247.9",
                "impact": "high",  # lowercase must resolve to HIGH, not default MEDIUM
                "screener_fields": ["age"],
                "evaluation_logic": "member.age >= 60",
            }
        ],
        "criteria_cannot_evaluate": [],
        "summary": "fixed",
        "recommendations": ["r1"],
    }
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeLLM(_fenced(payload)))
    state = ResearchState(**_BASE, field_mapping=_field_mapping(), research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    assert out["field_mapping"].criteria_can_evaluate[0].criterion == "age >= 60 CORRECTED"
    assert out["field_mapping"].criteria_can_evaluate[0].impact == ImpactLevel.HIGH
    assert all(issue.resolved for issue in out["research_qa_result"].issues)


@pytest.mark.asyncio
async def test_fix_research_leaves_mapping_unchanged_on_bad_response(monkeypatch):
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeLLM("no json here"))
    state = ResearchState(**_BASE, field_mapping=_field_mapping(), research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    assert "field_mapping" not in out


@pytest.mark.asyncio
async def test_fix_research_noop_without_field_mapping(monkeypatch):
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeLLM("unused"))
    state = ResearchState(**_BASE, field_mapping=None, research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    assert "field_mapping" not in out


# ---------------------------------------------------------------------------
# fix_test_cases_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_test_cases_applies_corrections(monkeypatch):
    payload = {
        "test_cases": [
            {
                "scenario_number": 1,
                "title": "FIXED TITLE",
                "category": "happy_path",
                "expected_eligible": True,
                "expected_amount": 600,
                "steps": [{"section": "Location", "instructions": ["Enter ZIP `60601`"]}],
                "what_to_look_for": ["eligible"],
                "why_matters": "w",
                "zip_code": "60601",
                "county": "Cook",
                "household_size": 1,
                "members_data": [{"relationship": "headOfHousehold"}],
                "current_benefits": {},
                "citizenship_status": "citizen",
            }
        ]
    }
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeLLM(_fenced(payload)))
    state = ResearchState(**_BASE, test_suite=_scenario_suite(), test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert out["test_suite"].test_cases[0].title == "FIXED TITLE"
    assert out["test_suite"].test_cases[0].expected_amount == 600
    assert all(issue.resolved for issue in out["test_case_qa_result"].issues)


@pytest.mark.asyncio
async def test_fix_test_cases_leaves_suite_unchanged_on_bad_response(monkeypatch):
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeLLM("garbage, no json"))
    state = ResearchState(**_BASE, test_suite=_scenario_suite(), test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert "test_suite" not in out


@pytest.mark.asyncio
async def test_fix_test_cases_noop_without_suite(monkeypatch):
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeLLM("unused"))
    state = ResearchState(**_BASE, test_suite=None, test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert "test_suite" not in out


# ---------------------------------------------------------------------------
# fix_json_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_json_applies_corrections(monkeypatch):
    payload = {
        "test_cases": [
            {
                "notes": "notes FIXED",
                "household": {
                    "white_label": "il",
                    "household_size": 1,
                    "zipcode": "60601",
                    "county": "Cook",
                    "expenses": [],
                    "household_members": [
                        {
                            "relationship": "headOfHousehold",
                            "birth_month": 3,
                            "birth_year": 1953,
                            "age": 72,
                            "income_streams": [],
                        }
                    ],
                },
                "expected_results": {"program_name": "il_csfp", "eligible": True, "value": 600},
            }
        ]
    }
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeLLM(_fenced(payload)))
    state = ResearchState(
        **_BASE,
        test_suite=_scenario_suite(),
        json_test_cases=[_json_test_case()],
        json_qa_result=_qa_result("json"),
    )

    out = await cj.fix_json_node(state)

    assert out["json_test_cases"][0].notes == "notes FIXED"
    assert out["json_test_cases"][0].expected_results.value == 600
    assert all(issue.resolved for issue in out["json_qa_result"].issues)


@pytest.mark.asyncio
async def test_fix_json_leaves_json_unchanged_on_bad_response(monkeypatch):
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeLLM("nope"))
    state = ResearchState(
        **_BASE,
        test_suite=_scenario_suite(),
        json_test_cases=[_json_test_case()],
        json_qa_result=_qa_result("json"),
    )

    out = await cj.fix_json_node(state)

    assert "json_test_cases" not in out


@pytest.mark.asyncio
async def test_fix_json_noop_without_json_test_cases(monkeypatch):
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeLLM("unused"))
    state = ResearchState(
        **_BASE, test_suite=_scenario_suite(), json_test_cases=[], json_qa_result=_qa_result("json")
    )

    out = await cj.fix_json_node(state)

    assert "json_test_cases" not in out
