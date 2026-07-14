"""Tests for the QA fix nodes (fix_research, fix_test_cases, fix_json).

Each node sends the current artifact plus the QA issues to the researcher model
and gets a corrected artifact back via structured output (with_structured_output),
which returns an already-validated Pydantic object. The LLM is stubbed so the
tests exercise the guard / state-update / leave-unchanged logic deterministically.
"""

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
    JSONTestCaseSuite,
    QAIssue,
    QAValidationResult,
    ResearchState,
    ScenarioStep,
    ScenarioSuite,
)


class _FakeStructuredLLM:
    """Stands in for ``ChatAnthropic(...).with_structured_output(Schema)``.

    Constructed with any kwargs; ``with_structured_output`` returns self. On
    ``ainvoke`` it either returns the canned parsed object or raises the given
    error, mirroring how structured output raises when the model cannot produce
    a valid instance of the schema.
    """

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def __call__(self, *args, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        return self

    async def ainvoke(self, _messages):
        if self._error is not None:
            raise self._error
        return self._result


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


def _json_test_case(notes="old notes", value=100) -> JSONTestCase:
    return JSONTestCase(
        notes=notes,
        household=JSONTestCaseHousehold(
            white_label="il",
            household_size=1,
            zipcode="60601",
            county="Cook",
            household_members=[
                JSONTestCaseMember(relationship="headOfHousehold", birth_month=3, birth_year=1953, age=72)
            ],
        ),
        expected_results=JSONTestCaseExpectedResults(program_name="il_csfp", eligible=True, value=value),
    )


# ---------------------------------------------------------------------------
# fix_research_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_research_applies_corrections(monkeypatch):
    # Structured output returns a FieldMapping directly. Note impact="high"
    # (lowercase) must resolve to HIGH via the model validator, and the data-gap
    # criterion's screener_fields must be forced to None by normalization.
    corrected = FieldMapping(
        program_name="ignored-should-be-overridden",
        criteria_can_evaluate=[
            EligibilityCriterion(
                criterion="age >= 60 CORRECTED",
                source_reference="7 CFR 247.9",
                impact="high",
                screener_fields=["age"],
                evaluation_logic="member.age >= 60",
            )
        ],
        criteria_cannot_evaluate=[
            EligibilityCriterion(
                criterion="not institutionalized",
                source_reference="manual",
                screener_fields=["should_be_nulled"],
                evaluation_logic="should_be_nulled",
            )
        ],
        summary="fixed",
        recommendations=["r1"],
    )
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeStructuredLLM(result=corrected))
    state = ResearchState(**_BASE, field_mapping=_field_mapping(), research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    mapping = out["field_mapping"]
    assert mapping.program_name == "csfp"  # overridden from state, not the model
    assert mapping.criteria_can_evaluate[0].criterion == "age >= 60 CORRECTED"
    assert mapping.criteria_can_evaluate[0].impact == ImpactLevel.HIGH
    # Data gaps must have screener_fields / evaluation_logic forced to None
    assert mapping.criteria_cannot_evaluate[0].screener_fields is None
    assert mapping.criteria_cannot_evaluate[0].evaluation_logic is None
    assert all(issue.resolved for issue in out["research_qa_result"].issues)


@pytest.mark.asyncio
async def test_fix_research_leaves_mapping_unchanged_when_output_invalid(monkeypatch):
    # Structured output raises when the model cannot produce a valid schema.
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeStructuredLLM(error=ValueError("no tool call")))
    state = ResearchState(**_BASE, field_mapping=_field_mapping(), research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    assert "field_mapping" not in out
    assert not any(issue.resolved for issue in state.research_qa_result.issues)


@pytest.mark.asyncio
async def test_fix_research_noop_without_field_mapping(monkeypatch):
    monkeypatch.setattr(qa, "ChatAnthropic", _FakeStructuredLLM(result=None))
    state = ResearchState(**_BASE, field_mapping=None, research_qa_result=_qa_result("research"))

    out = await qa.fix_research_node(state)

    assert "field_mapping" not in out


# ---------------------------------------------------------------------------
# fix_test_cases_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_test_cases_applies_corrections(monkeypatch):
    # current_benefits carries a string "yes" to confirm the boolean coercion
    # validator runs on structured-output results too.
    fixed_tc = HumanTestCase(
        scenario_number=1,
        title="FIXED TITLE",
        what_checking="w",
        category="happy_path",
        expected_eligible=True,
        expected_amount=600,
        steps=[ScenarioStep(section="Location", instructions=["Enter ZIP `60601`"])],
        what_to_look_for=["eligible"],
        why_matters="w",
        zip_code="60601",
        county="Cook",
        household_size=1,
        members_data=[{"relationship": "headOfHousehold"}],
        current_benefits={"snap": "yes"},
    )
    corrected = ScenarioSuite(program_name="m", white_label="m", test_cases=[fixed_tc])
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeStructuredLLM(result=corrected))
    state = ResearchState(**_BASE, test_suite=_scenario_suite(), test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    suite = out["test_suite"]
    assert suite.program_name == "csfp"  # identity preserved from state
    assert suite.white_label == "il"
    assert suite.test_cases[0].title == "FIXED TITLE"
    assert suite.test_cases[0].expected_amount == 600
    assert suite.test_cases[0].current_benefits == {"snap": True}
    assert all(issue.resolved for issue in out["test_case_qa_result"].issues)


@pytest.mark.asyncio
async def test_fix_test_cases_leaves_suite_unchanged_when_output_invalid(monkeypatch):
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeStructuredLLM(error=ValueError("bad output")))
    state = ResearchState(**_BASE, test_suite=_scenario_suite(), test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert "test_suite" not in out
    assert not any(issue.resolved for issue in state.test_case_qa_result.issues)


@pytest.mark.asyncio
async def test_fix_test_cases_leaves_suite_unchanged_when_empty(monkeypatch):
    # A schema-valid but empty suite must be treated as a no-op.
    empty = ScenarioSuite(program_name="m", white_label="m", test_cases=[])
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeStructuredLLM(result=empty))
    state = ResearchState(**_BASE, test_suite=_scenario_suite(), test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert "test_suite" not in out


@pytest.mark.asyncio
async def test_fix_test_cases_noop_without_suite(monkeypatch):
    monkeypatch.setattr(gt, "ChatAnthropic", _FakeStructuredLLM(result=None))
    state = ResearchState(**_BASE, test_suite=None, test_case_qa_result=_qa_result("test_cases"))

    out = await gt.fix_test_cases_node(state)

    assert "test_suite" not in out


# ---------------------------------------------------------------------------
# fix_json_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_json_applies_corrections(monkeypatch):
    corrected = JSONTestCaseSuite(test_cases=[_json_test_case(notes="notes FIXED", value=600)])
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeStructuredLLM(result=corrected))
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
async def test_fix_json_leaves_json_unchanged_when_output_invalid(monkeypatch):
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeStructuredLLM(error=ValueError("bad output")))
    state = ResearchState(
        **_BASE,
        test_suite=_scenario_suite(),
        json_test_cases=[_json_test_case()],
        json_qa_result=_qa_result("json"),
    )

    out = await cj.fix_json_node(state)

    assert "json_test_cases" not in out
    assert not any(issue.resolved for issue in state.json_qa_result.issues)


@pytest.mark.asyncio
async def test_fix_json_leaves_json_unchanged_when_empty(monkeypatch):
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeStructuredLLM(result=JSONTestCaseSuite(test_cases=[])))
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
    monkeypatch.setattr(cj, "ChatAnthropic", _FakeStructuredLLM(result=None))
    state = ResearchState(
        **_BASE, test_suite=_scenario_suite(), json_test_cases=[], json_qa_result=_qa_result("json")
    )

    out = await cj.fix_json_node(state)

    assert "json_test_cases" not in out


# ---------------------------------------------------------------------------
# State-model validators that back the structured-output migration
# ---------------------------------------------------------------------------


def test_impact_validator_is_case_insensitive():
    assert EligibilityCriterion(criterion="c", source_reference="r", impact="high").impact == ImpactLevel.HIGH
    assert EligibilityCriterion(criterion="c", source_reference="r", impact="LOW").impact == ImpactLevel.LOW


def test_impact_validator_defaults_unknown_to_medium():
    crit = EligibilityCriterion(criterion="c", source_reference="r", impact="bogus")
    assert crit.impact == ImpactLevel.MEDIUM


def test_current_benefits_coercion_handles_strings_and_non_dict():
    tc = HumanTestCase(
        scenario_number=1,
        title="t",
        what_checking="w",
        category="happy_path",
        expected_eligible=False,
        steps=[],
        what_to_look_for=[],
        why_matters="w",
        zip_code="00000",
        county="Unknown",
        household_size=1,
        members_data="not-a-list",
        current_benefits={"snap": "yes", "tanf": "no", "wic": 1},
    )
    assert tc.current_benefits == {"snap": True, "tanf": False, "wic": True}
    assert tc.members_data == []
