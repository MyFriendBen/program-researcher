"""Tests for the criteria-extraction node's parsing and retry behavior.

These guard the "spec has no base criteria" symptom: extraction must recover from
prose-wrapped / fence-mangled LLM output, retry once, and — only when it truly
cannot parse — fail loudly (empty mapping + error_message) rather than silently.
"""

import json

import program_research_agent.nodes.extract_criteria as ec
import pytest
from program_research_agent.state import EligibilityCriterion, ImpactLevel, ResearchState

_GOOD_PAYLOAD = {
    "criteria_can_evaluate": [
        {"criterion": "age >= 60", "impact": "high", "screener_fields": ["age"]}
    ],
    "criteria_cannot_evaluate": [
        {"criterion": "asset test", "impact": "LOW"},
        "not-a-dict",  # must be skipped, not crash
    ],
    "summary": "coverage summary",
    "recommendations": ["r1"],
}


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


# ---------------------------------------------------------------------------
# parse_field_mapping
# ---------------------------------------------------------------------------


def test_parse_field_mapping_fenced_and_impact_case():
    fm = ec.parse_field_mapping(_fenced(_GOOD_PAYLOAD), "csfp")
    # lowercase "high"/"LOW" must resolve to the enum, not default to MEDIUM
    assert fm.criteria_can_evaluate[0].impact == ImpactLevel.HIGH
    assert fm.criteria_cannot_evaluate[0].impact == ImpactLevel.LOW
    # non-dict criterion entry is skipped
    assert len(fm.criteria_cannot_evaluate) == 1


def test_parse_field_mapping_prose_wrapped():
    text = "Sure, here you go:\n" + json.dumps(_GOOD_PAYLOAD) + "\nLet me know if you need more."
    fm = ec.parse_field_mapping(text, "csfp")
    assert fm.criteria_can_evaluate[0].criterion == "age >= 60"


def test_parse_field_mapping_data_gaps_have_no_screener_fields():
    payload = {
        "criteria_cannot_evaluate": [
            {"criterion": "x", "screener_fields": ["should_be_dropped"], "evaluation_logic": "nope"}
        ]
    }
    fm = ec.parse_field_mapping(_fenced(payload), "csfp")
    assert fm.criteria_cannot_evaluate[0].screener_fields is None
    assert fm.criteria_cannot_evaluate[0].evaluation_logic is None


@pytest.mark.parametrize("bad", ["totally not json", "", "```json\n{ broken", "[1, 2, 3]"])
def test_parse_field_mapping_raises_on_unusable(bad):
    with pytest.raises((json.JSONDecodeError, ValueError, TypeError)):
        ec.parse_field_mapping(bad, "csfp")


# ---------------------------------------------------------------------------
# extract_criteria_node (LLM stubbed)
# ---------------------------------------------------------------------------


class _Msg:
    """Minimal stand-in for an LLM message with a `.content` attribute."""

    def __init__(self, content=""):
        self.content = content


class _FakeStructured:
    """Return value of with_structured_output(...): its ainvoke yields the raw/parsed dict."""

    def __init__(self, result):
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class _FakeLLM:
    """Stands in for ChatAnthropic; with_structured_output returns a canned result dict."""

    def __init__(self, structured_result):
        self._structured_result = structured_result

    def __call__(self, *args, **kwargs):
        return self

    def with_structured_output(self, _schema, include_raw=False):
        return _FakeStructured(self._structured_result)


_BASE = {"program_name": "csfp", "state_code": "il", "white_label": "il", "source_urls": ["http://x"]}


@pytest.fixture(autouse=True)
def _stub_formatters(monkeypatch):
    # These need populated state from earlier nodes; stub them so the tests
    # isolate the LLM call + parse/retry logic.
    monkeypatch.setattr(ec, "format_fields_for_prompt", lambda *a, **k: "FIELDS")
    monkeypatch.setattr(ec, "format_link_catalog", lambda *a, **k: "LINKS")


async def test_extract_criteria_success_via_structured_output(monkeypatch):
    parsed = ec.ExtractionResult(
        criteria_can_evaluate=[
            EligibilityCriterion(criterion="age >= 60", source_reference="7 CFR", impact=ImpactLevel.HIGH)
        ],
        criteria_cannot_evaluate=[],
        summary="s",
        recommendations=["r1"],
    )
    result = {"raw": _Msg("<tool call>"), "parsed": parsed, "parsing_error": None}
    monkeypatch.setattr(ec, "ChatAnthropic", _FakeLLM(result))

    out = await ec.extract_criteria_node(ResearchState(**_BASE))

    assert out["field_mapping"].criteria_can_evaluate[0].criterion == "age >= 60"
    assert "error_message" not in out


async def test_extract_criteria_recovers_via_text_fallback(monkeypatch):
    # Model returned prose instead of a tool call — salvage it with the text parser.
    result = {
        "raw": _Msg(_fenced(_GOOD_PAYLOAD)),
        "parsed": None,
        "parsing_error": ValueError("no tool call"),
    }
    monkeypatch.setattr(ec, "ChatAnthropic", _FakeLLM(result))

    out = await ec.extract_criteria_node(ResearchState(**_BASE))

    assert out["field_mapping"].criteria_can_evaluate
    assert "error_message" not in out
    assert any("text-parse fallback" in m for m in out["messages"])


async def test_extract_criteria_fails_loudly(monkeypatch, tmp_path):
    result = {
        "raw": _Msg("totally not json"),
        "parsed": None,
        "parsing_error": ValueError("no tool call"),
    }
    monkeypatch.setattr(ec, "ChatAnthropic", _FakeLLM(result))

    out = await ec.extract_criteria_node(ResearchState(**_BASE, output_dir=str(tmp_path)))

    assert out["field_mapping"].criteria_can_evaluate == []
    assert "error_message" in out
    assert (tmp_path / "extract_criteria_raw_response.txt").exists()
