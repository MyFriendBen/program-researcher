"""
Node: Convert to JSON

Convert human-readable test cases to the benefits-api test_case_schema.json format.
"""

import json
from datetime import date
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import ResearchState, WorkflowStatus
from ..tools.schema_validator import fetch_schema, validate_test_case


async def convert_to_json_node(state: ResearchState) -> dict:
    """
    Convert human-readable test cases to JSON schema format.

    This node:
    1. Fetches the benefits-api schema from GitHub
    2. Converts each test case to the schema format
    3. Validates against the schema
    4. Returns validated JSON test cases
    """
    messages = list(state.messages)
    messages.append("Converting test cases to JSON format...")

    if not state.test_suite or not state.test_suite.test_cases:
        messages.append("No test cases to convert - cannot proceed")
        messages.append("This is a critical failure - JSON conversion skipped")
        return {
            "json_test_cases": [],
            "messages": messages,
            "status": WorkflowStatus.FAILED,
            "error_message": "No test cases available for JSON conversion",
        }

    # Convert each test case
    json_test_cases: list[dict[str, Any]] = []
    current_date = date.today()

    for tc in state.test_suite.test_cases:
        try:
            json_tc = convert_test_case(tc, state.white_label, state.program_name, current_date)
            json_test_cases.append(json_tc)
        except Exception as e:
            messages.append(f"Error converting scenario {tc.scenario_number}: {e}")

    messages.append(f"Converted {len(json_test_cases)} test cases to JSON")

    # Validate each test case against the fetched schema
    valid_count = 0
    for json_tc in json_test_cases:
        is_valid, errors = validate_test_case(json_tc)
        if is_valid:
            valid_count += 1
        else:
            notes = json_tc.get("notes", "unknown")
            messages.append(f"Validation errors in '{notes}': {errors[:2]}")

    messages.append(f"Schema validation: {valid_count}/{len(json_test_cases)} valid")

    return {
        "json_test_cases": json_test_cases,
        "messages": messages,
    }


def _build_income_streams(member_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build income_streams list from member data.

    Handles both the new income_streams format (list of dicts with type/amount/frequency)
    and the legacy flat income dict format (e.g. {"sSRetirement": 800, "income_frequency": "monthly"}).
    """
    # New format: income_streams already provided as a list
    if "income_streams" in member_data and isinstance(member_data["income_streams"], list):
        streams = []
        for stream in member_data["income_streams"]:
            if not isinstance(stream, dict):
                continue
            s: dict[str, Any] = {
                "type": stream.get("type", "other"),
                "amount": float(stream.get("amount", 0)),
                "frequency": stream.get("frequency", "monthly"),
            }
            if s["frequency"] == "hourly" and "hours_worked" in stream:
                s["hours_worked"] = int(stream["hours_worked"])
            streams.append(s)
        return streams

    # Legacy flat income dict format
    if "income" not in member_data or not member_data["income"]:
        return []

    income_data = member_data["income"]
    frequency = income_data.get("income_frequency", "monthly")
    hours_worked = income_data.get("hours_per_week") or income_data.get("hours_worked")

    # Income type field names in the flat format
    income_type_fields = [
        "wages",
        "selfEmployment",
        "sSDisability",
        "sSRetirement",
        "sSI",
        "sSSurvivor",
        "sSDependent",
        "unemployment",
        "cashAssistance",
        "cOSDisability",
        "workersComp",
        "veteran",
        "childSupport",
        "alimony",
        "gifts",
        "boarder",
        "pension",
        "investment",
        "rental",
        "deferredComp",
        "workersCompensation",
        "veteransBenefits",
        "rentalIncome",
        "other",
    ]

    streams = []
    for field in income_type_fields:
        amount = income_data.get(field)
        if amount is not None and float(amount) > 0:
            stream: dict[str, Any] = {
                "type": field,
                "amount": float(amount),
                "frequency": frequency,
            }
            if frequency == "hourly" and hours_worked is not None:
                stream["hours_worked"] = int(hours_worked)
            streams.append(stream)

    return streams


def convert_test_case(
    tc,
    white_label: str,
    program_name: str,
    current_date: date,
) -> dict[str, Any]:
    """
    Convert a single human test case to the benefits-api JSON schema format.

    New format:
    {
        "notes": "<white_label> <program_name> - <title>",
        "household": {
            "white_label": "...",
            "zipcode": "...",
            "county": "...",
            "agree_to_tos": true,
            "is_13_or_older": true,
            "household_members": [...],
            "expenses": [],
            "has_*": true/false,  # from current_benefits
        },
        "expected_results": {
            "program_name": "...",
            "eligible": true/false,
            "value": ...  # optional
        }
    }
    """
    # Build notes (human-readable identifier)
    notes = f"{white_label.upper()} {program_name} - {tc.title}"

    # Convert members
    members = []
    household_expenses: list[dict[str, Any]] = []

    for member_data in tc.members_data:
        # Calculate age from birth date
        birth_year = member_data.get("birth_year", 1990)
        birth_month = member_data.get("birth_month", 1)
        age = current_date.year - birth_year
        if current_date.month < birth_month:
            age -= 1

        # Build income_streams
        income_streams = _build_income_streams(member_data)
        has_income = bool(income_streams) or member_data.get("has_income", False)

        # Collect member expenses → move to household level
        if member_data.get("expenses") and isinstance(member_data["expenses"], dict):
            exp_data = member_data["expenses"]
            expense_type_map = {
                "rent": "rent",
                "mortgage": "mortgage",
                "childCare": "childCare",
                "childSupport": "childSupport",
                "medical": "medical",
                "heating": "heating",
                "cooling": "cooling",
            }
            for field, exp_type in expense_type_map.items():
                amount = exp_data.get(field)
                if amount is not None and float(amount) > 0:
                    household_expenses.append({
                        "type": exp_type,
                        "amount": float(amount),
                        "frequency": "monthly",
                    })

        # Build insurance object
        insurance_data = member_data.get("insurance", {})
        # Ensure insurance has `none: true` if nothing else is set
        insurance: dict[str, Any] = {
            "dont_know": insurance_data.get("dont_know", False),
            "none": insurance_data.get("none", True),
            "employer": insurance_data.get("employer", False),
            "private": insurance_data.get("private", False),
            "chp": insurance_data.get("chp", False),
            "medicaid": insurance_data.get("medicaid", False),
            "medicare": insurance_data.get("medicare", False),
            "emergency_medicaid": insurance_data.get("emergency_medicaid", False),
            "family_planning": insurance_data.get("family_planning", False),
            "va": insurance_data.get("va", False),
            "mass_health": insurance_data.get("mass_health", False),
        }
        # If any specific type is True, set none to False
        specific_types = ["employer", "private", "chp", "medicaid", "medicare",
                          "emergency_medicaid", "family_planning", "va", "mass_health"]
        if any(insurance.get(t, False) for t in specific_types):
            insurance["none"] = False

        member: dict[str, Any] = {
            "relationship": member_data.get("relationship", "headOfHousehold"),
            "age": age,
            "insurance": insurance,
        }

        # Optional boolean flags (new schema field names)
        flag_map = {
            "pregnant": ["pregnant", "is_pregnant"],
            "student": ["student", "is_student"],
            "disabled": ["disabled", "is_disabled"],
            "veteran": ["veteran", "is_veteran"],
            "visually_impaired": ["visually_impaired", "is_blind"],
            "unemployed": ["unemployed"],
            "worked_in_last_18_mos": ["worked_in_last_18_mos"],
            "long_term_disability": ["long_term_disability"],
            "medicaid": ["medicaid"],
            "disability_medicaid": ["disability_medicaid"],
        }
        for new_name, old_names in flag_map.items():
            for old_name in old_names:
                if old_name in member_data and member_data[old_name] is not None:
                    member[new_name] = bool(member_data[old_name])
                    break

        if has_income:
            member["has_income"] = True
        if income_streams:
            member["income_streams"] = income_streams

        # Include birth_year and birth_month if present (optional schema fields)
        if birth_year:
            member["birth_year"] = birth_year
        if birth_month:
            member["birth_month"] = birth_month

        members.append(member)

    # Build current_benefits → individual has_* fields on household
    has_fields: dict[str, bool] = {}
    for benefit_key, benefit_val in (tc.current_benefits or {}).items():
        # Normalize: "snap" → "has_snap", "has_snap" → "has_snap"
        normalized_key = benefit_key if benefit_key.startswith("has_") else f"has_{benefit_key}"
        has_fields[normalized_key] = bool(benefit_val)

    # Build household
    household: dict[str, Any] = {
        "white_label": white_label,
        "zipcode": tc.zip_code,
        "county": tc.county,
        "agree_to_tos": True,
        "is_13_or_older": True,
        "household_members": members,
        "expenses": household_expenses,
    }

    # Add optional household fields
    if tc.household_assets:
        household["household_assets"] = tc.household_assets
    if tc.household_size:
        household["household_size"] = tc.household_size

    # Add has_* benefit flags
    household.update(has_fields)

    # Build expected_results
    program_name_full = f"{white_label}_{program_name}".lower()
    expected_results: dict[str, Any] = {
        "program_name": program_name_full,
        "eligible": tc.expected_eligible,
    }
    if tc.expected_amount is not None:
        expected_results["value"] = tc.expected_amount

    return {
        "notes": notes,
        "household": household,
        "expected_results": expected_results,
    }


async def fix_json_node(state: ResearchState) -> dict:
    """
    Fix JSON conversion issues identified by QA.

    Parses the QA issues and asks the LLM to fix specific problems in the JSON test cases.
    """
    messages = list(state.messages)
    messages.append("Fixing JSON conversion issues...")

    if not state.json_qa_result or not state.json_qa_result.issues:
        messages.append("No JSON issues to fix")
        return {"messages": messages}

    # Format current JSON test cases for LLM
    current_json = json.dumps(state.json_test_cases, indent=2)

    # Format issues for LLM
    issues_text = "\n".join(
        f"- [{i.severity if isinstance(i.severity, str) else i.severity.value}] "
        f"{i.issue_type}: {i.description} (location: {i.location}) — Fix: {i.suggested_fix}"
        for i in state.json_qa_result.issues
    )

    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["fix_issues"].format(
        current_output=current_json,
        qa_issues=issues_text,
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCHER_PROMPTS["system"]),
                HumanMessage(content=prompt),
            ]
        )

        response_text = response.content
        if isinstance(response_text, list):
            response_text = response_text[0].get("text", "") if response_text else ""

        # Extract JSON from response
        json_match = response_text
        if "```json" in response_text:
            json_match = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_match = response_text.split("```")[1].split("```")[0]

        fixed_cases = json.loads(json_match)

        if isinstance(fixed_cases, list):
            messages.append(f"Fixed {len(fixed_cases)} JSON test cases")
            return {
                "json_test_cases": fixed_cases,
                "messages": messages,
            }
        else:
            messages.append("LLM returned unexpected format for fixed cases")
    except Exception as e:
        messages.append(f"Error fixing JSON issues: {e}")

    messages.append(f"Addressed {len(state.json_qa_result.issues)} JSON issues")
    return {"messages": messages}
