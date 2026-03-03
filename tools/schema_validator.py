"""
JSON Schema validation tools.

Validates test cases against the test_case_schema.json fetched from benefits-api.
"""

import json
from typing import Any

import requests
from jsonschema import Draft7Validator, ValidationError

from ..config import settings

# Module-level schema cache — fetched once per process
_schema_cache: dict[str, Any] = {}


def fetch_schema() -> dict[str, Any]:
    """
    Fetch the JSON schema from the configured URL, caching the result.

    Returns the parsed JSON schema dict. Raises on fetch/parse failure.
    """
    url = settings.schema_url
    if url in _schema_cache:
        return _schema_cache[url]

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        schema = response.json()
        _schema_cache[url] = schema
        return schema
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch schema from {url}: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in schema from {url}: {e}") from e


def load_schema() -> dict[str, Any]:
    """
    Load the JSON schema (fetched from configured URL).

    Returns the parsed JSON schema dict.
    """
    return fetch_schema()


def validate_test_case(test_case: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate a single test case against the benefits-api schema.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    try:
        schema = fetch_schema()
        validator = Draft7Validator(schema)

        errors = []
        for error in validator.iter_errors(test_case):
            path = " -> ".join(str(p) for p in error.absolute_path) or "root"
            errors.append(f"{path}: {error.message}")

        if errors:
            return False, errors
        return True, []

    except RuntimeError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Validation error: {e}"]


def check_required_fields(test_case: dict[str, Any]) -> list[str]:
    """
    Check that all required fields are present in a test case.

    Returns list of missing required field paths.
    """
    missing = []

    # Top-level required (new format: notes, household, expected_results)
    for field in ["notes", "household", "expected_results"]:
        if field not in test_case:
            missing.append(field)

    # Household required
    if "household" in test_case:
        household = test_case["household"]
        for field in ["white_label", "household_members", "expenses"]:
            if field not in household:
                missing.append(f"household.{field}")

        # Member required
        if "household_members" in household:
            for i, member in enumerate(household["household_members"]):
                for field in ["relationship", "age", "insurance"]:
                    if field not in member:
                        missing.append(f"household.household_members[{i}].{field}")

    # Expected results required — handles both object and array
    if "expected_results" in test_case:
        er = test_case["expected_results"]
        if isinstance(er, dict):
            for field in ["program_name", "eligible"]:
                if field not in er:
                    missing.append(f"expected_results.{field}")
        elif isinstance(er, list):
            for i, item in enumerate(er):
                for field in ["program_name", "eligible"]:
                    if field not in item:
                        missing.append(f"expected_results[{i}].{field}")

    return missing


def validate_enum_values(test_case: dict[str, Any]) -> list[str]:
    """
    Validate that enum fields have valid values.

    Returns list of invalid enum value errors.
    """
    errors = []

    # Valid relationship values (17 total — matches updated schema)
    valid_relationships = [
        "headOfHousehold",
        "child",
        "fosterChild",
        "stepChild",
        "grandChild",
        "spouse",
        "parent",
        "fosterParent",
        "stepParent",
        "grandParent",
        "sisterOrBrother",
        "stepSisterOrBrother",
        "boyfriendOrGirlfriend",
        "domesticPartner",
        "relatedOther",
        "unrelated",
        "other",
    ]

    valid_housing = ["rent", "own", "staying_with_friends", "hotel", "shelter", "other"]

    valid_income_frequency = ["weekly", "biweekly", "semimonthly", "monthly", "yearly", "hourly"]

    if "household" in test_case:
        household = test_case["household"]

        # Housing situation (at household level)
        if "housing_situation" in household:
            if household["housing_situation"] not in valid_housing:
                errors.append(
                    f"Invalid housing_situation: {household['housing_situation']}. "
                    f"Must be one of: {valid_housing}"
                )

        # Members (new key: household_members)
        if "household_members" in household:
            for i, member in enumerate(household["household_members"]):
                if "relationship" in member:
                    if member["relationship"] not in valid_relationships:
                        errors.append(
                            f"household.household_members[{i}].relationship: Invalid value "
                            f"'{member['relationship']}'. Must be one of: {valid_relationships}"
                        )

                # Income streams (new format: income_streams[].frequency)
                for j, stream in enumerate(member.get("income_streams", [])):
                    if "frequency" in stream:
                        freq = stream["frequency"]
                        if freq not in valid_income_frequency:
                            errors.append(
                                f"household.household_members[{i}].income_streams[{j}].frequency: "
                                f"Invalid value '{freq}'. Must be one of: {valid_income_frequency}"
                            )

    return errors


def format_validation_report(
    test_case: dict[str, Any],
    schema_errors: list[str],
    missing_fields: list[str],
    enum_errors: list[str],
) -> str:
    """Format a validation report for a test case."""
    # Use 'notes' as identifier (new format), fall back to 'test_id' for legacy
    identifier = test_case.get("notes", test_case.get("test_id", "unknown"))
    lines = [f"## Validation Report: {identifier}\n"]

    if not schema_errors and not missing_fields and not enum_errors:
        lines.append("✅ **VALID** - All checks passed\n")
        return "\n".join(lines)

    lines.append("❌ **INVALID** - Issues found:\n")

    if missing_fields:
        lines.append("### Missing Required Fields")
        for field in missing_fields:
            lines.append(f"- `{field}`")
        lines.append("")

    if enum_errors:
        lines.append("### Invalid Enum Values")
        for error in enum_errors:
            lines.append(f"- {error}")
        lines.append("")

    if schema_errors:
        lines.append("### Schema Validation Errors")
        for error in schema_errors:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines)
