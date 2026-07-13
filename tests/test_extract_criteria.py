"""Tests for the criteria-extraction node's parsing and retry behavior.

These guard the "spec has no base criteria" symptom: extraction must recover from
prose-wrapped / fence-mangled LLM output, retry once, and — only when it truly
cannot parse — fail loudly (empty mapping + error_message) rather than silently.
"""

import json

import program_research_agent.nodes.extract_criteria as ec
import pytest
from program_research_agent.state import ImpactLevel, ResearchState

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


class _Resp:
    def __init__(self, text):
        self.content = text


class _SequenceLLM:
    """Returns a queued response per ainvoke call (for testing retry)."""

    def __init__(self, texts):
        self._texts = list(texts)
        self._i = 0

    def __call__(self, *args, **kwargs):
        return self

    async def ainvoke(self, _messages):
        text = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        return _Resp(text)


_BASE = {"program_name": "csfp", "state_code": "il", "white_label": "il", "source_urls": ["http://x"]}


@pytest.fixture(autouse=True)
def _stub_formatters(monkeypatch):
    # These need populated state from earlier nodes; stub them so the tests
    # isolate the LLM call + parse/retry logic.
    monkeypatch.setattr(ec, "format_fields_for_prompt", lambda *a, **k: "FIELDS")
    monkeypatch.setattr(ec, "format_link_catalog", lambda *a, **k: "LINKS")


async def test_extract_criteria_success_first_attempt(monkeypatch):
    monkeypatch.setattr(ec, "ChatAnthropic", _SequenceLLM([_fenced(_GOOD_PAYLOAD)]))
    out = await ec.extract_criteria_node(ResearchState(**_BASE))
    assert out["field_mapping"].criteria_can_evaluate
    assert "error_message" not in out


async def test_extract_criteria_recovers_on_retry(monkeypatch):
    monkeypatch.setattr(
        ec, "ChatAnthropic", _SequenceLLM(["I could not format that", _fenced(_GOOD_PAYLOAD)])
    )
    out = await ec.extract_criteria_node(ResearchState(**_BASE))
    assert out["field_mapping"].criteria_can_evaluate
    assert "error_message" not in out
    assert any("Attempt 1" in m for m in out["messages"])


async def test_extract_criteria_fails_loudly_after_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(ec, "ChatAnthropic", _SequenceLLM(["no json", "still no json"]))
    out = await ec.extract_criteria_node(ResearchState(**_BASE, output_dir=str(tmp_path)))
    assert out["field_mapping"].criteria_can_evaluate == []
    assert "error_message" in out
    assert (tmp_path / "extract_criteria_raw_response.txt").exists()
