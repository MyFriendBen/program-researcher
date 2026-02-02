"""
Tools for reading screener field definitions from the codebase.

Parses Django models and TypeScript types to understand what data
the screener collects.
"""

import ast
import re
from datetime import date
from pathlib import Path

from ..config import settings
from ..state import ScreenerField, ScreenerFieldCatalog


def get_screener_fields() -> ScreenerFieldCatalog:
    """
    Read screener field definitions from the codebase.

    Parses:
    - benefits-be/screener/models.py for Django model fields
    - benefits-fe/src/Types/FormData.ts for frontend type definitions

    Returns:
        ScreenerFieldCatalog with all available fields
    """
    catalog = ScreenerFieldCatalog(last_updated=date.today())

    # Parse Django models
    if settings.backend_models_path.exists():
        django_fields = parse_django_models(settings.backend_models_path)
        catalog.screen_fields = django_fields.get("Screen", [])
        catalog.household_member_fields = django_fields.get("HouseholdMember", [])
        catalog.income_fields = django_fields.get("IncomeStream", [])
        catalog.expense_fields = django_fields.get("Expense", [])
        catalog.insurance_fields = django_fields.get("Insurance", [])
        catalog.helper_methods = django_fields.get("_helper_methods", [])

    # Parse TypeScript types for additional fields
    if settings.frontend_types_path.exists():
        ts_fields = parse_typescript_types(settings.frontend_types_path)
        # Merge any frontend-only fields
        for field in ts_fields:
            if field.model == "FormData" and not any(
                f.name == field.name for f in catalog.screen_fields
            ):
                # Mark as frontend-only
                field.description = f"[Frontend Only] {field.description}"
                catalog.screen_fields.append(field)

    return catalog


def parse_django_models(models_path: Path) -> dict[str, list[ScreenerField]]:
    """
    Parse Django model definitions to extract field information.

    Uses AST parsing to find class definitions and field assignments.
    """
    result: dict[str, list[ScreenerField]] = {
        "Screen": [],
        "HouseholdMember": [],
        "IncomeStream": [],
        "Expense": [],
        "Insurance": [],
        "_helper_methods": [],
    }

    try:
        content = models_path.read_text()
        tree = ast.parse(content)

        # Track which model we're in
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                model_name = node.name
                if model_name not in result:
                    continue

                for item in node.body:
                    # Parse field definitions
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                field_info = extract_django_field(target.id, item.value, content)
                                if field_info:
                                    field_info.model = model_name
                                    result[model_name].append(field_info)

                    # Parse helper methods
                    if isinstance(item, ast.FunctionDef) and model_name == "Screen":
                        if item.name.startswith(("calc_", "get_", "has_", "num_", "is_")):
                            # Extract method signature
                            args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                            signature = f"{item.name}({', '.join(args)})"
                            result["_helper_methods"].append(signature)

        # Also extract choice values from the file
        choice_patterns = extract_choice_constants(content)
        for model_name, fields in result.items():
            if model_name.startswith("_"):
                continue
            for field in fields:
                if field.name in choice_patterns:
                    field.valid_values = choice_patterns[field.name]

    except Exception as e:
        # If parsing fails, return empty but log the error
        print(f"Warning: Failed to parse Django models: {e}")

    return result


def extract_django_field(name: str, value: ast.expr, full_content: str) -> ScreenerField | None:
    """Extract field information from a Django field assignment."""
    if not isinstance(value, ast.Call):
        return None

    # Get the field type name
    field_type = ""
    if isinstance(value.func, ast.Attribute):
        field_type = value.func.attr
    elif isinstance(value.func, ast.Name):
        field_type = value.func.id

    # Only process Django field types
    django_field_types = {
        "CharField",
        "TextField",
        "IntegerField",
        "PositiveIntegerField",
        "FloatField",
        "DecimalField",
        "BooleanField",
        "NullBooleanField",
        "DateField",
        "DateTimeField",
        "ForeignKey",
        "OneToOneField",
        "ManyToManyField",
    }

    if field_type not in django_field_types:
        return None

    # Extract description from help_text or verbose_name
    description = name.replace("_", " ").title()
    valid_values = None

    for keyword in value.keywords:
        if keyword.arg == "help_text" and isinstance(keyword.value, ast.Constant):
            description = str(keyword.value.value)
        elif keyword.arg == "verbose_name" and isinstance(keyword.value, ast.Constant):
            description = str(keyword.value.value)
        elif keyword.arg == "choices":
            # Try to extract choices
            if isinstance(keyword.value, ast.Name):
                # Reference to a constant - look it up
                choices_name = keyword.value.id
                valid_values = extract_choices_by_name(choices_name, full_content)

    return ScreenerField(
        name=name,
        field_type=field_type,
        description=description,
        valid_values=valid_values,
        model="",  # Set by caller
    )


def extract_choices_by_name(choices_name: str, content: str) -> list[str] | None:
    """Extract choice values from a named constant in the file."""
    # Look for patterns like:
    # CHOICES_NAME = [('value', 'label'), ...]
    # or
    # CHOICES_NAME = (('value', 'label'), ...)

    pattern = rf"{choices_name}\s*=\s*[\[\(](.*?)[\]\)]"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None

    choices_str = match.group(1)
    # Extract the first element of each tuple (the value)
    value_pattern = r"\(\s*['\"]([^'\"]+)['\"]"
    values = re.findall(value_pattern, choices_str)
    return values if values else None


def extract_choice_constants(content: str) -> dict[str, list[str]]:
    """Extract all choice constants from the models file."""
    results = {}

    # Look for TYPE_CHOICES, STATUS_CHOICES, etc.
    pattern = r"(\w+_CHOICES)\s*=\s*[\[\(](.*?)[\]\)]"
    for match in re.finditer(pattern, content, re.DOTALL):
        name = match.group(1)
        choices_str = match.group(2)

        # Extract values
        value_pattern = r"\(\s*['\"]([^'\"]+)['\"]"
        values = re.findall(value_pattern, choices_str)
        if values:
            # Map to likely field names
            field_name = name.replace("_CHOICES", "").lower()
            results[field_name] = values
            results["type"] = values  # Common field name

    return results


def parse_typescript_types(types_path: Path) -> list[ScreenerField]:
    """
    Parse TypeScript type definitions for frontend-only fields.

    This is a simplified parser - for complex types, consider using
    a proper TypeScript parser.
    """
    fields = []

    try:
        content = types_path.read_text()

        # Look for interface or type definitions
        # Pattern: fieldName: Type;  or  fieldName?: Type;
        field_pattern = r"(\w+)\??:\s*([^;]+);"

        for match in re.finditer(field_pattern, content):
            name = match.group(1)
            ts_type = match.group(2).strip()

            # Convert TypeScript type to a description
            field_type = "unknown"
            if "string" in ts_type:
                field_type = "string"
            elif "number" in ts_type:
                field_type = "number"
            elif "boolean" in ts_type:
                field_type = "boolean"
            elif "[]" in ts_type:
                field_type = "array"

            # Extract enum values if present
            valid_values = None
            if "|" in ts_type:
                # Could be a union type like 'value1' | 'value2'
                values = re.findall(r"['\"]([^'\"]+)['\"]", ts_type)
                if values:
                    valid_values = values

            # Convert camelCase to Title Case
            description = re.sub(r"([A-Z])", r" \1", name).strip().title()

            fields.append(
                ScreenerField(
                    name=name,
                    field_type=field_type,
                    description=description,
                    valid_values=valid_values,
                    model="FormData",
                )
            )

    except Exception as e:
        print(f"Warning: Failed to parse TypeScript types: {e}")

    return fields


def format_fields_for_prompt(catalog: ScreenerFieldCatalog) -> str:
    """Format the field catalog as a string for use in prompts."""
    sections = []

    if catalog.screen_fields:
        sections.append("## Screen (Household) Level Fields\n")
        sections.append("| Field | Type | Description | Valid Values |")
        sections.append("|-------|------|-------------|--------------|")
        for field in catalog.screen_fields:
            values = ", ".join(field.valid_values[:5]) if field.valid_values else "-"
            if field.valid_values and len(field.valid_values) > 5:
                values += "..."
            sections.append(f"| {field.name} | {field.field_type} | {field.description} | {values} |")
        sections.append("")

    if catalog.household_member_fields:
        sections.append("## HouseholdMember Level Fields\n")
        sections.append("| Field | Type | Description | Valid Values |")
        sections.append("|-------|------|-------------|--------------|")
        for field in catalog.household_member_fields:
            values = ", ".join(field.valid_values[:5]) if field.valid_values else "-"
            sections.append(f"| {field.name} | {field.field_type} | {field.description} | {values} |")
        sections.append("")

    if catalog.income_fields:
        sections.append("## IncomeStream Fields\n")
        sections.append("| Field | Type | Description | Valid Values |")
        sections.append("|-------|------|-------------|--------------|")
        for field in catalog.income_fields:
            values = ", ".join(field.valid_values[:5]) if field.valid_values else "-"
            sections.append(f"| {field.name} | {field.field_type} | {field.description} | {values} |")
        sections.append("")

    if catalog.expense_fields:
        sections.append("## Expense Fields\n")
        sections.append("| Field | Type | Description | Valid Values |")
        sections.append("|-------|------|-------------|--------------|")
        for field in catalog.expense_fields:
            values = ", ".join(field.valid_values[:5]) if field.valid_values else "-"
            sections.append(f"| {field.name} | {field.field_type} | {field.description} | {values} |")
        sections.append("")

    if catalog.helper_methods:
        sections.append("## Helper Methods Available\n")
        for method in catalog.helper_methods:
            sections.append(f"- `screen.{method}`")
        sections.append("")

    return "\n".join(sections)
