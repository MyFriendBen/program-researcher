"""
JSON Schema validation tools.

Validates test cases against the benefits-api test_case_schema.json fetched from GitHub.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from jsonschema import Draft7Validator

from ..config import settings

# Module-level cache: fetched once per process
_schema_cache: dict[str, Any] = {}


def fetch_schema() -> dict[str, Any]:
    """Fetch the JSON schema from settings.schema_url, caching per process."""
    url = settings.schema_url
    if url not in _schema_cache:
        with urllib.request.urlopen(url, timeout=10) as response:
            _schema_cache[url] = json.loads(response.read().decode())
    return _schema_cache[url]


def validate_against_schema(
    data: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate a test case dict against the fetched JSON schema.

    Args:
        data: The test case dict to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    try:
        schema = fetch_schema()
        validator = Draft7Validator(schema)

        errors = []
        for error in validator.iter_errors(data):
            path = " -> ".join(str(p) for p in error.absolute_path) or "root"
            errors.append(f"{path}: {error.message}")

        if errors:
            return False, errors
        return True, []

    except urllib.error.URLError as e:
        return False, [f"Failed to fetch schema: {e}"]

    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in schema: {e}"]

    except Exception as e:
        return False, [f"Validation error: {e}"]


def validate_test_case(test_case: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate a single test case against the benefits-api schema.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    return validate_against_schema(test_case)


def check_required_fields(test_case: dict[str, Any]) -> list[str]:
    """
    Check that all required fields are present in a test case.

    Returns list of missing required field paths.
    """
    missing = []

    # Top-level required
    for field in ["notes", "household", "expected_results"]:
        if field not in test_case:
            missing.append(field)

    # Household required
    if "household" in test_case:
        household = test_case["household"]
        for field in ["household_members", "zipcode", "agree_to_tos"]:
            if field not in household:
                missing.append(f"household.{field}")

        # Member required
        if "household_members" in household:
            for i, member in enumerate(household["household_members"]):
                for field in ["relationship", "age", "insurance"]:
                    if field not in member:
                        missing.append(f"household.household_members[{i}].{field}")

    # Expected results required
    if "expected_results" in test_case:
        if "eligible" not in test_case["expected_results"]:
            missing.append("expected_results.eligible")

    return missing


def validate_enum_values(test_case: dict[str, Any]) -> list[str]:
    """
    Validate that enum fields have valid values.

    Returns list of invalid enum value errors.
    """
    errors = []

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
    ]

    valid_housing = ["rent", "own", "staying_with_friends", "hotel", "shelter", "other"]

    if "household" in test_case:
        household = test_case["household"]

        # Housing situation
        if "housing_situation" in household:
            if household["housing_situation"] not in valid_housing:
                errors.append(
                    f"Invalid housing_situation: {household['housing_situation']}. "
                    f"Must be one of: {valid_housing}"
                )

        # Members
        if "household_members" in household:
            for i, member in enumerate(household["household_members"]):
                if "relationship" in member:
                    if member["relationship"] not in valid_relationships:
                        errors.append(
                            f"household.household_members[{i}].relationship: Invalid value "
                            f"'{member['relationship']}'. Must be one of: {valid_relationships}"
                        )

    return errors


def format_validation_report(
    test_case: dict[str, Any],
    schema_errors: list[str],
    missing_fields: list[str],
    enum_errors: list[str],
) -> str:
    """Format a validation report for a test case."""
    lines = [f"## Validation Report: {test_case.get('notes', 'unknown')}\n"]

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
