"""
State definitions for the Program Research Agent.

This module defines all the Pydantic models and TypedDict state used
throughout the LangGraph workflow.
"""

from datetime import date
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class LinkCategory(str, Enum):
    """Categories for discovered documentation links."""

    OFFICIAL_PROGRAM = "Official Program"
    LEGISLATION = "Legislation"
    REGULATION = "Regulation"
    APPLICATION = "Application"
    RESEARCH = "Research"
    NAVIGATOR = "Navigator"


class ImpactLevel(str, Enum):
    """Impact level for data gaps or issues."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IssueSeverity(str, Enum):
    """Severity levels for QA issues."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class WorkflowStatus(str, Enum):
    """Overall workflow status."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    AWAITING_INPUT = "awaiting_input"


# -----------------------------------------------------------------------------
# Step 1: Link Catalog Models
# -----------------------------------------------------------------------------


class LinkCatalogEntry(BaseModel):
    """A single link discovered during research."""

    category: LinkCategory = Field(description="Category of the link")
    title: str = Field(description="Descriptive title for the link")
    url: str = Field(description="Full URL")
    source_type: str = Field(description="Type of source (Federal Agency, State Agency, etc.)")
    found_in: str = Field(
        description="Where the link was found ('Provided' or 'Referenced in [source]')"
    )
    accessible: bool = Field(default=True, description="Whether the URL is accessible")
    content_summary: str | None = Field(
        default=None, description="Brief summary of the content at this URL"
    )


class LinkCatalog(BaseModel):
    """Complete catalog of links for a program."""

    program_name: str
    state_code: str
    research_date: date
    sources_provided: int
    links: list[LinkCatalogEntry] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Step 2: Screener Field Models
# -----------------------------------------------------------------------------


class ScreenerField(BaseModel):
    """A field available in the screener."""

    name: str = Field(description="Field name as it appears in code")
    field_type: str = Field(description="Data type (CharField, IntegerField, etc.)")
    description: str = Field(description="Human-readable description")
    valid_values: list[str] | None = Field(
        default=None, description="Valid values for choice fields"
    )
    model: str = Field(description="Which model this field belongs to")


class ScreenerFieldCatalog(BaseModel):
    """Complete catalog of available screener fields."""

    screen_fields: list[ScreenerField] = Field(default_factory=list)
    household_member_fields: list[ScreenerField] = Field(default_factory=list)
    income_fields: list[ScreenerField] = Field(default_factory=list)
    expense_fields: list[ScreenerField] = Field(default_factory=list)
    insurance_fields: list[ScreenerField] = Field(default_factory=list)
    helper_methods: list[str] = Field(
        default_factory=list, description="Available helper methods for calculations"
    )
    last_updated: date | None = Field(default=None)


# -----------------------------------------------------------------------------
# Step 3: Eligibility Criteria Models
# -----------------------------------------------------------------------------


class EligibilityCriterion(BaseModel):
    """A single eligibility criterion extracted from documentation."""

    criterion: str = Field(description="The eligibility requirement in plain language")
    source_reference: str = Field(
        description="Citation to source (e.g., '7 CFR 247.9(a)' or 'State manual p.12')"
    )
    source_url: str | None = Field(default=None, description="URL where this was found")
    screener_fields: list[str] | None = Field(
        default=None,
        description="Screener field(s) that can evaluate this. None = data gap",
    )
    evaluation_logic: str | None = Field(
        default=None, description="How to evaluate (e.g., 'member.age >= 60')"
    )
    notes: str = Field(default="", description="Additional notes about this criterion")
    impact: ImpactLevel = Field(
        default=ImpactLevel.MEDIUM,
        description="Impact if this criterion cannot be evaluated",
    )


class FieldMapping(BaseModel):
    """Complete mapping of program criteria to screener fields."""

    program_name: str
    criteria_can_evaluate: list[EligibilityCriterion] = Field(default_factory=list)
    criteria_cannot_evaluate: list[EligibilityCriterion] = Field(default_factory=list)
    summary: str = Field(default="", description="Summary of mapping coverage")
    recommendations: list[str] = Field(
        default_factory=list, description="Recommendations for gaps"
    )


# -----------------------------------------------------------------------------
# Step 5: Test Case Models
# -----------------------------------------------------------------------------


class ScenarioStep(BaseModel):
    """A single step in a test case."""

    section: str = Field(description="Form section (Location, Household, Person 1, etc.)")
    instructions: list[str] = Field(description="Specific instructions for this section")


class HumanTestCase(BaseModel):
    """A human-readable test scenario."""

    scenario_number: int = Field(description="Scenario identifier")
    title: str = Field(description="Brief descriptive title")
    what_checking: str = Field(description="Plain language explanation of what this tests")
    category: str = Field(
        description="Category: happy_path, income_threshold, age_threshold, geographic, exclusion, edge_case, multi_member"
    )
    expected_eligible: bool = Field(description="Should this person/household qualify?")
    expected_amount: float | None = Field(
        default=None, description="Expected benefit amount per year"
    )
    expected_time: str | None = Field(
        default=None, description="Expected application time"
    )
    steps: list[ScenarioStep] = Field(description="Step-by-step instructions")
    what_to_look_for: list[str] = Field(
        description="What to verify on the results page"
    )
    why_matters: str = Field(description="Plain language explanation of why this test matters")

    # Data needed for JSON conversion
    zip_code: str = Field(description="ZIP code to use")
    county: str = Field(description="County name")
    household_size: int = Field(description="Number of household members")
    household_assets: float = Field(default=0, description="Total household assets")
    members_data: list[dict[str, Any]] = Field(
        description="Structured data for each household member"
    )
    current_benefits: dict[str, bool] = Field(
        default_factory=dict, description="Current benefits checkboxes"
    )
    citizenship_status: str = Field(default="citizen", description="Citizenship/legal status")


class ScenarioSuite(BaseModel):
    """Complete suite of test cases for a program."""

    program_name: str
    white_label: str
    test_cases: list[HumanTestCase] = Field(default_factory=list)
    coverage_summary: str = Field(default="", description="Summary of what's covered")


# -----------------------------------------------------------------------------
# QA Models
# -----------------------------------------------------------------------------


class QAIssue(BaseModel):
    """An issue found during QA validation."""

    severity: IssueSeverity = Field(description="How serious is this issue")
    issue_type: str = Field(
        description="Type: missed_criterion, incorrect_mapping, wrong_threshold, missing_test, incorrect_value, schema_mismatch"
    )
    description: str = Field(description="What the issue is")
    location: str = Field(description="Where in the output the issue was found")
    source_reference: str | None = Field(
        default=None, description="Citation supporting this issue"
    )
    suggested_fix: str = Field(description="How to fix this issue")
    resolved: bool = Field(default=False, description="Whether this issue has been resolved")


class QAValidationResult(BaseModel):
    """Result of a QA validation pass."""

    validation_type: str = Field(
        description="What was validated: research, test_cases, json"
    )
    overall_status: Literal["VALIDATED", "VALIDATED_WITH_CONCERNS", "NEEDS_REVISION"] = Field(
        description="Overall assessment"
    )
    issues: list[QAIssue] = Field(default_factory=list)
    summary: str = Field(description="Summary of validation")
    recommendation: str = Field(description="Proceed or revise")


# -----------------------------------------------------------------------------
# JSON Output Models (matches pre_validation_schema.json)
# -----------------------------------------------------------------------------


class JSONTestCaseMemberIncome(BaseModel):
    """Income data for a household member in JSON format."""

    wages: float | None = None
    selfEmployment: float | None = None
    unemployment: float | None = None
    sSI: float | None = None
    sSDisability: float | None = None
    sSRetirement: float | None = None
    sSSurvivor: float | None = None
    sSDependent: float | None = None
    pension: float | None = None
    veteran: float | None = None
    cashAssistance: float | None = None
    childSupport: float | None = None
    alimony: float | None = None
    investment: float | None = None
    rental: float | None = None
    income_frequency: str = "monthly"
    hours_per_week: float | None = None


class JSONTestCaseMemberExpenses(BaseModel):
    """Expense data for a household member in JSON format."""

    rent: float | None = None
    mortgage: float | None = None
    childCare: float | None = None
    childSupport: float | None = None
    medical: float | None = None
    heating: float | None = None
    cooling: float | None = None


class JSONTestCaseMemberInsurance(BaseModel):
    """Insurance data for a household member in JSON format."""

    none: bool = False
    employer: bool = False
    private: bool = False
    medicaid: bool = False
    medicare: bool = False
    chp: bool = False
    va: bool = False


class JSONTestCaseMember(BaseModel):
    """A household member in JSON test case format."""

    relationship: str
    birth_month: int
    birth_year: int
    age: int | None = None  # Calculated
    gender: str | None = None
    is_pregnant: bool | None = None
    is_student: bool | None = None
    is_disabled: bool | None = None
    is_veteran: bool | None = None
    is_blind: bool | None = None
    unemployed: bool | None = None
    has_income: bool | None = None
    income: JSONTestCaseMemberIncome | None = None
    expenses: JSONTestCaseMemberExpenses | None = None
    insurance: JSONTestCaseMemberInsurance = Field(default_factory=JSONTestCaseMemberInsurance)


class JSONTestCaseHousehold(BaseModel):
    """Household data in JSON test case format."""

    household_size: int
    zip_code: str
    county: str
    household_assets: float = 0
    agree_to_terms_of_service: bool = True
    is_13_or_older: bool = True
    housing_situation: str | None = None
    has_benefits: str | None = None
    current_benefits: dict[str, bool] | None = None
    members: list[JSONTestCaseMember]


class JSONTestCaseExpectedResults(BaseModel):
    """Expected results in JSON test case format."""

    eligibility: bool
    benefit_amount: float | None = None
    copay: float | None = None


class JSONTestCase(BaseModel):
    """A complete JSON test case matching pre_validation_schema.json."""

    test_id: str
    white_label: str
    program_name: str
    household: JSONTestCaseHousehold
    expected_results: JSONTestCaseExpectedResults


# -----------------------------------------------------------------------------
# Linear Ticket Model
# -----------------------------------------------------------------------------


class LinearTicketContent(BaseModel):
    """Content for creating a Linear ticket."""

    title: str
    description: str
    acceptance_criteria: list[str]
    test_scenarios_summary: str
    source_documentation: list[str]
    json_test_file_path: str | None = None


# -----------------------------------------------------------------------------
# Main Graph State
# -----------------------------------------------------------------------------


class ResearchState(BaseModel):
    """
    Complete state for the research workflow.

    This is the main state object that flows through the LangGraph.
    """

    # ----- Input -----
    program_name: str = Field(description="Name of the benefit program")
    state_code: str = Field(description="State code (e.g., 'il', 'co', 'nc')")
    white_label: str = Field(description="White label identifier")
    source_urls: list[str] = Field(description="Source documentation URLs provided by user")

    # ----- Step 1: Link Discovery -----
    link_catalog: LinkCatalog | None = Field(default=None)

    # ----- Step 2: Screener Fields -----
    screener_fields: ScreenerFieldCatalog | None = Field(default=None)

    # ----- Step 3: Field Mapping -----
    field_mapping: FieldMapping | None = Field(default=None)

    # ----- Research QA Loop -----
    research_qa_result: QAValidationResult | None = Field(default=None)
    research_iteration: int = Field(default=0)

    # ----- Step 5: Test Cases -----
    test_suite: ScenarioSuite | None = Field(default=None)

    # ----- Test Case QA Loop -----
    test_case_qa_result: QAValidationResult | None = Field(default=None)
    test_case_iteration: int = Field(default=0)

    # ----- JSON Conversion -----
    json_test_cases: list[JSONTestCase] = Field(default_factory=list)

    # ----- JSON QA Loop -----
    json_qa_result: QAValidationResult | None = Field(default=None)
    json_iteration: int = Field(default=0)

    # ----- Linear Ticket -----
    linear_ticket: LinearTicketContent | None = Field(default=None)
    linear_ticket_url: str | None = Field(default=None)
    linear_ticket_id: str | None = Field(default=None)

    # ----- Control -----
    max_iterations: int = Field(default=3, description="Max QA iterations before proceeding")
    status: WorkflowStatus = Field(default=WorkflowStatus.IN_PROGRESS)
    error_message: str | None = Field(default=None)
    messages: list[str] = Field(
        default_factory=list, description="Log of workflow progress messages"
    )

    model_config = {"use_enum_values": True}


# -----------------------------------------------------------------------------
# State update helpers for LangGraph reducers
# -----------------------------------------------------------------------------


def add_message(messages: list[str], new_message: str) -> list[str]:
    """Reducer to append a message to the messages list."""
    return messages + [new_message]


def increment_counter(current: int, _: Any) -> int:
    """Reducer to increment a counter."""
    return current + 1
