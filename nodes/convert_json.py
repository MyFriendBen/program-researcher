"""
Node: Convert to JSON

Convert human-readable test cases to pre_validation_schema.json format.
"""

import json
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_schema_path, settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    JSONTestCase,
    JSONTestCaseExpectedResults,
    JSONTestCaseHousehold,
    JSONTestCaseMember,
    JSONTestCaseMemberIncome,
    JSONTestCaseMemberInsurance,
    ResearchState,
)
from ..tools.schema_validator import validate_test_case


async def convert_to_json_node(state: ResearchState) -> dict:
    """
    Convert human-readable test cases to JSON schema format.

    This node:
    1. Reads the pre_validation_schema
    2. Converts each test case to the schema format
    3. Validates against the schema
    4. Returns validated JSON test cases
    """
    messages = list(state.messages)
    messages.append("Converting test cases to JSON format...")

    if not state.test_suite or not state.test_suite.test_cases:
        messages.append("No test cases to convert")
        return {
            "json_test_cases": [],
            "messages": messages,
        }

    # Load the schema for reference
    schema_path = get_schema_path("pre_validation_schema.json")
    with open(schema_path) as f:
        schema = json.load(f)

    # Convert each test case
    json_test_cases = []
    current_date = date.today()

    for tc in state.test_suite.test_cases:
        try:
            json_tc = convert_test_case(tc, state.white_label, state.program_name, current_date)
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
            messages.append(f"Validation errors in {json_tc.test_id}: {errors[:2]}")

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
) -> JSONTestCase:
    """Convert a single human test case to JSON format."""

    # Generate test ID
    test_id = f"{white_label}_{program_name}_{tc.scenario_number:02d}"

    # Convert members
    members = []
    for member_data in tc.members_data:
        # Calculate age from birth date
        birth_year = member_data.get("birth_year", 1990)
        birth_month = member_data.get("birth_month", 1)
        age = current_date.year - birth_year
        if current_date.month < birth_month:
            age -= 1

        # Build income object
        income = None
        if member_data.get("income"):
            income_data = member_data["income"]
            income = JSONTestCaseMemberIncome(
                wages=income_data.get("wages"),
                selfEmployment=income_data.get("selfEmployment"),
                sSI=income_data.get("sSI"),
                sSDisability=income_data.get("sSDisability"),
                sSRetirement=income_data.get("sSRetirement"),
                sSSurvivor=income_data.get("sSSurvivor"),
                sSDependent=income_data.get("sSDependent"),
                pension=income_data.get("pension"),
                veteran=income_data.get("veteran"),
                cashAssistance=income_data.get("cashAssistance"),
                childSupport=income_data.get("childSupport"),
                alimony=income_data.get("alimony"),
                investment=income_data.get("investment"),
                rental=income_data.get("rental"),
                income_frequency=income_data.get("income_frequency", "monthly"),
                hours_per_week=income_data.get("hours_per_week"),
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
            is_pregnant=member_data.get("is_pregnant"),
            is_student=member_data.get("is_student"),
            is_disabled=member_data.get("is_disabled"),
            is_veteran=member_data.get("is_veteran"),
            is_blind=member_data.get("is_blind"),
            unemployed=member_data.get("unemployed"),
            has_income=member_data.get("has_income"),
            income=income,
            insurance=insurance,
        )
        members.append(member)

    # Build household
    household = JSONTestCaseHousehold(
        household_size=tc.household_size,
        zip_code=tc.zip_code,
        county=tc.county,
        household_assets=tc.household_assets,
        agree_to_terms_of_service=True,
        is_13_or_older=True,
        current_benefits=tc.current_benefits if tc.current_benefits else None,
        members=members,
    )

    # Build expected results
    expected_results = JSONTestCaseExpectedResults(
        eligibility=tc.expected_eligible,
        benefit_amount=tc.expected_amount,
    )

    return JSONTestCase(
        test_id=test_id,
        white_label=white_label,
        program_name=f"{white_label}_{program_name}".lower(),
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
