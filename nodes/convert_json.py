"""
Node: Convert to JSON

Convert human-readable test cases to benefits-api test_case_schema.json format.
"""

import json
import urllib.error
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

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
        is_valid, errors = validate_test_case(json_tc.model_dump(exclude_none=True))
        if is_valid:
            valid_count += 1
        else:
            messages.append(f"Validation errors in {json_tc.notes}: {errors[:2]}")

    messages.append(f"Schema validation: {valid_count}/{len(json_test_cases)} valid")

    return {
        "json_test_cases": json_test_cases,
        "messages": messages,
    }


def _normalize_county(county: str, white_label: str) -> str:
    """Strip 'County' suffix for TX/IL per schema requirements."""
    if white_label in ("tx", "il") and county.lower().endswith(" county"):
        return county[: -len(" county")].strip()
    return county


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
        county=_normalize_county(tc.county, white_label),
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

    Sends the current JSON test cases plus the QA issues (and the human-readable
    source scenarios for reference) to the researcher model, parses the corrected
    array back into JSONTestCase objects, and re-validates against the schema so
    the next QA pass sees the improved version.

    On any parse failure the original JSON is left intact and the iteration
    counter bounds the loop.
    """
    messages = list(state.messages)
    messages.append("Fixing JSON conversion issues...")

    if not state.json_qa_result or not state.json_qa_result.issues:
        messages.append("No JSON issues to fix")
        return {"messages": messages}

    if not state.json_test_cases:
        messages.append("No JSON test cases available to fix")
        return {"messages": messages}

    from .extract_criteria import extract_json_block
    from .qa_research import format_qa_issues
    from .qa_tests import format_test_cases

    current_json = json.dumps(
        [tc.model_dump(exclude_none=True) for tc in state.json_test_cases], indent=2
    )
    human_source = format_test_cases(state.test_suite)
    issues_text = format_qa_issues(state.json_qa_result.issues)

    llm = ChatAnthropic(
        model=settings.researcher_model,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        max_retries=settings.model_max_retries,
        api_key=settings.anthropic_api_key,
    )

    prompt = RESEARCHER_PROMPTS["fix_json"].format(
        program_name=state.program_name,
        white_label=state.white_label,
        current_output=current_json,
        human_test_cases=human_source,
        qa_issues=issues_text,
        current_date=date.today().isoformat(),
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=RESEARCHER_PROMPTS["system"]),
            HumanMessage(content=prompt),
        ]
    )

    response_text = response.content
    if isinstance(response_text, list):
        response_text = response_text[0].get("text", "") if response_text else ""

    try:
        data = json.loads(extract_json_block(response_text))
        raw_cases = data.get("test_cases", data) if isinstance(data, dict) else data
        if not isinstance(raw_cases, list) or not raw_cases:
            raise ValueError("No test cases in fix response")
        fixed_json_cases = [
            JSONTestCase.model_validate(item) for item in raw_cases if isinstance(item, dict)
        ]
        if not fixed_json_cases:
            raise ValueError("No valid test cases parsed from fix response")
    except (json.JSONDecodeError, KeyError, ValueError, ValidationError) as e:
        # Leave the JSON unchanged; qa_validate_json will re-flag on the next pass
        # and the iteration counter bounds the loop.
        messages.append(f"Could not parse fix response ({e}); leaving JSON unchanged")
        return {"messages": messages}

    # Re-validate the repaired cases against the schema for logging.
    valid_count = sum(
        1 for tc in fixed_json_cases if validate_test_case(tc.model_dump(exclude_none=True))[0]
    )

    for issue in state.json_qa_result.issues:
        issue.resolved = True

    messages.append(
        f"Applied fixes for {len(state.json_qa_result.issues)} issues; "
        f"schema validation: {valid_count}/{len(fixed_json_cases)} valid"
    )

    return {
        "json_test_cases": fixed_json_cases,
        "json_qa_result": state.json_qa_result,
        "messages": messages,
    }
