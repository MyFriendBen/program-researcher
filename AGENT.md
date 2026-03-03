# AGENT.md — Program Research Agent

Build and test learnings for the program-researcher LangGraph agent.

## Package Structure

The directory is named `program-researcher` (hyphen) but the Python package is `program_research_agent` (underscore). This aliasing is done in `tests/conftest.py` via `sys.modules`:

```python
# tests/conftest.py
import sys, types
sys.modules["program_research_agent"] = types.ModuleType("program_research_agent")
```

Always import from `program_research_agent.*`, never from `program_researcher.*`.

## Running Tests

```bash
cd program-researcher
pip install -e ".[dev]"
pytest
```

All 12 tests should pass in ~0.03s (no I/O; no LLM calls).

### Test Infrastructure Notes

- `pyproject.toml` has `[tool.pytest.ini_options]` with `--import-mode=importlib` — **required** to avoid import errors when pytest collects `__init__.py` as a standalone module.
- `tests/__init__.py` must **not exist** — its presence causes pytest to walk up and try to import the root `__init__.py` as a package entry point, which breaks relative imports.
- `__init__.py` wraps all relative imports in `try/except ImportError` — pytest may import it standalone during test discovery.

## Dependencies

- `requests` is used in `tools/schema_validator.py` for fetching the schema from GitHub. It must be listed in `pyproject.toml` **and** `requirements.txt`. (`httpx` is also a dependency but `requests` is used for the synchronous schema fetch.)
- `jsonschema` with `Draft7Validator` is used for schema validation.

## Schema Validation Architecture

Schema is fetched **once per process** from GitHub via `tools/schema_validator.fetch_schema()`:

```
settings.schema_url (RESEARCH_AGENT_SCHEMA_URL env var)
  → requests.get() with 30s timeout
  → cached in _schema_cache dict (module-level)
  → Draft7Validator for validation
```

Default URL: `https://raw.githubusercontent.com/MyFriendBen/benefits-api/main/validations/management/commands/import_validations/test_case_schema.json`

To use a local schema during development:
```bash
export RESEARCH_AGENT_SCHEMA_URL="file:///path/to/local/test_case_schema.json"
```

## JSON Test Case Format (New — post MFB-723)

```json
{
  "notes": "IL CSFP - Eligible elderly low-income household",
  "household": {
    "white_label": "il",
    "zipcode": "60601",
    "agree_to_tos": true,
    "housing_situation": "rent",
    "has_snap": false,
    "household_members": [
      {
        "relationship": "headOfHousehold",
        "age": 65,
        "pregnant": false,
        "student": false,
        "disabled": false,
        "veteran": false,
        "visually_impaired": false,
        "insurance": {},
        "income_streams": [
          {"type": "sSRetirement", "amount": 800, "frequency": "monthly"}
        ]
      }
    ],
    "expenses": []
  },
  "expected_results": {
    "program_name": "CSFP",
    "eligible": true,
    "value": 0
  }
}
```

**Key field renames from old format:**
| Old | New |
|-----|-----|
| `test_id` | removed (use `notes` string) |
| `white_label` (top-level) | `household.white_label` |
| `program_name` (top-level) | `expected_results.program_name` |
| `zip_code` | `household.zipcode` |
| `agree_to_terms_of_service` | `household.agree_to_tos` |
| `members` | `household.household_members` |
| `is_pregnant` | `pregnant` |
| `is_student` | `student` |
| `is_disabled` | `disabled` |
| `is_veteran` | `veteran` |
| `is_blind` | `visually_impaired` |
| `income: {sSRetirement: 800}` | `income_streams: [{type, amount, frequency}]` |
| `eligibility` | `eligible` |
| `benefit_amount` | `value` |
| `current_benefits: {snap: true}` | `has_snap: true` (on household) |

## LangGraph Workflow Nodes

```
link_discovery → scrape_content → read_screener_fields → field_mapping
  → research_qa → [loop back or proceed]
  → generate_tests → test_case_qa → [loop back or proceed]
  → convert_json → json_qa → [loop back or proceed]
  → generate_program_config → create_linear_ticket → output_saver
```

## Configuration (Environment Variables)

All prefixed with `RESEARCH_AGENT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `SCHEMA_URL` | GitHub raw URL | Benefits-API schema URL |
| `RESEARCHER_MODEL` | `claude-sonnet-4-5-20250929` | Model for research nodes |
| `QA_MODEL` | `claude-opus-4-6` | Model for QA nodes |
| `LINEAR_API_KEY` | optional | For ticket creation |
| `LINEAR_TEAM_ID` | optional | Linear team for tickets |
| `LINEAR_PROJECT_ID` | optional | Linear project for tickets |

## Common Issues

### `ImportError: attempted relative import with no known parent package`
- Cause: pytest imports `__init__.py` standalone during test discovery
- Fix: `__init__.py` wraps imports in `try/except ImportError` + `--import-mode=importlib` in pyproject.toml

### `RuntimeError: Failed to fetch schema from ...`
- Cause: network unreachable or GitHub URL changed
- Fix: Set `RESEARCH_AGENT_SCHEMA_URL` to a local file path or accessible mirror

### `validate_test_case()` returns empty errors but JSON is wrong
- The schema uses `additionalProperties: false` in some nested objects — extra fields cause validation errors
- Check `format_validation_report()` output for exact error paths

## Remaining Work (from fix_plan.md)

- **H2**: `nodes/generate_tests.py` — implement `fix_test_cases_node()` (currently placeholder)
- **J1**: Update `README.md` — remove `schemas_dir` refs, add `RESEARCH_AGENT_SCHEMA_URL` config option
- End-to-end verification: run `python run.py research ...` against a real program URL
