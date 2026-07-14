"""Guards the web form's Decision-tag dropdowns against enum drift.

The reported traceback came from index.html submitting tier values ("state-calc",
"eligibility") that were not valid Tier enum members, so ResearchState() raised a
ValidationError in the worker. These tests fail if the template and the enums drift
apart again.
"""

import re
from pathlib import Path

import program_research_agent
from program_research_agent.state import Engine, Tier

_TEMPLATE = Path(program_research_agent.__path__[0]) / "web" / "templates" / "index.html"


def _option_values(select_name: str) -> list[str]:
    html = _TEMPLATE.read_text(encoding="utf-8")
    block = html.split(f'name="{select_name}"', 1)[1].split("</select>", 1)[0]
    # Ignore the empty "(not specified)" placeholder option.
    return [v for v in re.findall(r'option value="([^"]*)"', block) if v]


def test_tier_options_match_enum():
    values = _option_values("tier")
    valid = {t.value for t in Tier}
    assert values, "no tier options found in template"
    assert set(values) <= valid, f"template tier values not in Tier enum: {set(values) - valid}"


def test_engine_options_match_enum():
    values = _option_values("engine")
    valid = {e.value for e in Engine}
    assert values, "no engine options found in template"
    assert set(values) <= valid, f"template engine values not in Engine enum: {set(values) - valid}"


def test_tier_enum_fully_covered_by_template():
    values = set(_option_values("tier"))
    valid = {t.value for t in Tier}
    assert not (valid - values), f"Tier enum values missing from template: {valid - values}"


def test_engine_enum_fully_covered_by_template():
    values = set(_option_values("engine"))
    valid = {e.value for e in Engine}
    assert not (valid - values), f"Engine enum values missing from template: {valid - values}"


def test_state_custom_tier_is_selectable():
    # The specific option that triggered the reported traceback.
    assert Tier.STATE.value in _option_values("tier")
