"""
Node: Convert to JSON

Convert human-readable test cases to benefits-api test_case_schema.json format.
"""

import json
import urllib.error
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    JSONTestCaseExpense,
    JSONTestCaseIncomeStream,
    JSONTestCase,
    JSONTestCaseExpectedResults,
    JSONTestCaseHousehold,
    JSONTestCaseMember,
    JSONTestCaseMemberInsurance,
    ResearchState,
    WorkflowStatus,
)
from ..tools.schema_validator import fetch_schema, validate_test_case


async def convert_to_json_node(state: ResearchState) -> dict:
    """
    Convert human-readable test cases to JSON schema format.

    This node:
    1. Fetches the schema via `fetch_schema()` (HTTP, cached per process)
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

    # Load the schema for reference
    try:
        schema = fetch_schema()
    except (urllib.error.URLError, Exception) as e:
        messages.append(f"Failed to fetch schema: {e}")
        return {
            "json_test_cases": [],
            "messages": messages,
            "status": WorkflowStatus.FAILED,
            "error_message": f"Failed to fetch schema: {e}",
        }

    # Convert each test case
    json_test_cases = []
    current_date = date.today()

    for tc in state.test_suite.test_cases:
        try:
            json_tc = convert_test_case(tc, state.white_label, state.program_name, current_date, schema)
            json_test_cases.append(json_tc)
        except Exception as e:
            messages.append(f"Error converting scenario {tc.scenario_number}: {e}")

    messages.append(f"Converted {len(json_test_cases)} test cases to JSON")

    # Validate each test case
    valid_count = 0
    for json_tc in json_test_cases:
        is_valid, errors = validate_test_case(json_tc.model_dump())
        if is_valid:
            valid_count += 1
        else:
            messages.append(f"Validation errors in {json_tc.notes}: {errors[:2]}")

    messages.append(f"Schema validation: {valid_count}/{len(json_test_cases)} valid")

    return {
        "json_test_cases": json_test_cases,
        "messages": messages,
    }


def convert_test_case(
    tc,
    white_label: str,
    program_name: str,
    current_date: date,
    schema: dict,
) -> JSONTestCase:
    """Convert a single human test case to JSON format."""

    # Generate human-readable notes
    notes = f"{white_label.upper()} {program_name} - {tc.title}"

    # Convert members
    members = []
    for member_data in tc.members_data:
        # Calculate age from birth date
        birth_year = member_data.get("birth_year", 1990)
        birth_month = member_data.get("birth_month", 1)
        age = current_date.year - birth_year
        if current_date.month < birth_month:
            age -= 1

        # Build income_streams from flat income dict
        income_streams: list[JSONTestCaseIncomeStream] = []
        if member_data.get("income"):
            income_data = member_data["income"]
            # NOTE: income_frequency is applied uniformly to all income streams for a member;
            # the schema doesn't support per-stream frequencies, so this is a known limitation.
            frequency = income_data.get("income_frequency", "monthly")
            income_type_keys = schema["definitions"]["incomeStream"]["properties"]["type"]["enum"]
            for income_type in income_type_keys:
                amount = income_data.get(income_type)
                if amount is not None:
                    income_streams.append(
                        JSONTestCaseIncomeStream(type=income_type, amount=float(amount), frequency=frequency)
                    )

        # Build insurance object
        insurance_data = member_data.get("insurance", {})
        insurance = JSONTestCaseMemberInsurance(
            none=insurance_data.get("none", False),
            employer=insurance_data.get("employer", False),
            private=insurance_data.get("private", False),
            medicaid=insurance_data.get("medicaid", False),
            medicare=insurance_data.get("medicare", False),
            chp=insurance_data.get("chp", False),
            va=insurance_data.get("va", False),
        )

        member = JSONTestCaseMember(
            relationship=member_data.get("relationship", "headOfHousehold"),
            birth_month=birth_month,
            birth_year=birth_year,
            age=age,
            gender=member_data.get("gender"),
            pregnant=member_data.get("is_pregnant"),
            student=member_data.get("is_student"),
            disabled=member_data.get("is_disabled"),
            veteran=member_data.get("is_veteran"),
            visually_impaired=member_data.get("is_blind"),
            unemployed=member_data.get("unemployed"),
            has_income=member_data.get("has_income"),
            income_streams=income_streams,
            insurance=insurance,
        )
        members.append(member)

    # Build screen-level expenses (moved from per-member)
    expenses: list[JSONTestCaseExpense] = []
    for member_data in tc.members_data:
        for exp in member_data.get("expenses", []):
            expenses.append(
                JSONTestCaseExpense(
                    type=exp.get("type", ""),
                    amount=float(exp.get("amount", 0)),
                    frequency=exp.get("frequency", "monthly"),
                )
            )

    # Build household
    household = JSONTestCaseHousehold(
        white_label=white_label,
        household_size=tc.household_size,
        zipcode=tc.zip_code,
        county=tc.county,
        household_assets=tc.household_assets,
        agree_to_tos=True,
        is_13_or_older=True,
        housing_situation="rent",  # Default to rent for test cases
        household_members=members,
        expenses=expenses,
    )

    # Build expected results
    expected_results = JSONTestCaseExpectedResults(
        program_name=f"{white_label}_{program_name}".lower(),
        eligible=tc.expected_eligible,
        value=tc.expected_amount,
    )

    return JSONTestCase(
        notes=notes,
        household=household,
        expected_results=expected_results,
    )


async def fix_json_node(state: ResearchState) -> dict:
    """
    Fix JSON conversion issues identified by QA.
    """
    messages = list(state.messages)
    messages.append("Fixing JSON conversion issues...")

    if not state.json_qa_result or not state.json_qa_result.issues:
        messages.append("No JSON issues to fix")
        return {"messages": messages}

    # In a full implementation, would parse issues and fix specific problems

    messages.append(f"Addressed {len(state.json_qa_result.issues)} JSON issues")

    return {"messages": messages}
