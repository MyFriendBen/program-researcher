"""
JSON Schema validation tools.

Validates test cases against the pre_validation_schema.json.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from jsonschema import Draft7Validator, RefResolver, ValidationError, validate

from ..config import get_schema_path, settings


def load_schema(schema_name: str = "pre_validation_schema.json") -> dict[str, Any]:
    """Load a JSON schema from the schemas directory."""
    schema_path = get_schema_path(schema_name)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    with open(schema_path) as f:
        return json.load(f)


def get_schema_resolver() -> RefResolver:
    """
    Create a RefResolver that can resolve $ref references in schemas.

    This allows the batch schema to reference the main schema.
    """
    # Load the main schema for the resolver's store
    main_schema = load_schema("pre_validation_schema.json")

    # Create a resolver with the schemas directory as the base URI
    schema_dir = settings.schemas_dir.resolve()
    base_uri = f"file://{schema_dir}/"

    # Build a schema store for local resolution
    store = {
        base_uri + "pre_validation_schema.json": main_schema,
        "./pre_validation_schema.json": main_schema,
        "pre_validation_schema.json": main_schema,
    }

    return RefResolver(base_uri, main_schema, store=store)


def validate_against_schema(
    data: dict[str, Any] | list[dict[str, Any]],
    schema_name: str = "pre_validation_schema.json",
) -> tuple[bool, list[str]]:
    """
    Validate data against a JSON schema.

    Args:
        data: The data to validate (single test case or batch)
        schema_name: Name of the schema file

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    try:
        # Determine which schema to use based on data type
        if isinstance(data, list):
            schema = load_schema("pre_validation_batch_schema.json")
        else:
            schema = load_schema(schema_name)

        # Create resolver for $ref handling
        resolver = get_schema_resolver()

        # Create validator with resolver
        validator = Draft7Validator(schema, resolver=resolver)

        # Collect all validation errors
        errors = []
        for error in validator.iter_errors(data):
            path = " -> ".join(str(p) for p in error.absolute_path) or "root"
            errors.append(f"{path}: {error.message}")

        if errors:
            return False, errors
        return True, []

    except FileNotFoundError as e:
        return False, [str(e)]

    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON in schema: {e}"]

    except Exception as e:
        return False, [f"Validation error: {e}"]


def validate_test_case(test_case: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate a single test case against the pre_validation_schema.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    return validate_against_schema(test_case, "pre_validation_schema.json")


def validate_test_batch(test_cases: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """
    Validate a batch of test cases against the pre_validation_batch_schema.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    return validate_against_schema(test_cases, "pre_validation_batch_schema.json")


def check_required_fields(test_case: dict[str, Any]) -> list[str]:
    """
    Check that all required fields are present in a test case.

    Returns list of missing required field paths.
    """
    missing = []

    # Top-level required
    for field in ["test_id", "white_label", "program_name", "household", "expected_results"]:
        if field not in test_case:
            missing.append(field)

    # Household required
    if "household" in test_case:
        household = test_case["household"]
        for field in [
            "household_size",
            "zip_code",
            "county",
            "agree_to_terms_of_service",
            "is_13_or_older",
            "household_assets",
            "members",
        ]:
            if field not in household:
                missing.append(f"household.{field}")

        # Member required
        if "members" in household:
            for i, member in enumerate(household["members"]):
                for field in ["relationship", "birth_month", "birth_year", "insurance"]:
                    if field not in member:
                        missing.append(f"household.members[{i}].{field}")

    # Expected results required
    if "expected_results" in test_case:
        if "eligibility" not in test_case["expected_results"]:
            missing.append("expected_results.eligibility")

    return missing


def validate_enum_values(test_case: dict[str, Any]) -> list[str]:
    """
    Validate that enum fields have valid values.

    Returns list of invalid enum value errors.
    """
    errors = []

    # Valid relationship values
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

    valid_income_frequency = ["weekly", "biweekly", "semimonthly", "monthly", "yearly", "hourly"]

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
        if "members" in household:
            for i, member in enumerate(household["members"]):
                if "relationship" in member:
                    if member["relationship"] not in valid_relationships:
                        errors.append(
                            f"household.members[{i}].relationship: Invalid value "
                            f"'{member['relationship']}'. Must be one of: {valid_relationships}"
                        )

                if "income" in member and member["income"]:
                    if "income_frequency" in member["income"]:
                        freq = member["income"]["income_frequency"]
                        if freq not in valid_income_frequency:
                            errors.append(
                                f"household.members[{i}].income.income_frequency: Invalid value "
                                f"'{freq}'. Must be one of: {valid_income_frequency}"
                            )

    return errors


def format_validation_report(
    test_case: dict[str, Any],
    schema_errors: list[str],
    missing_fields: list[str],
    enum_errors: list[str],
) -> str:
    """Format a validation report for a test case."""
    lines = [f"## Validation Report: {test_case.get('test_id', 'unknown')}\n"]

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
