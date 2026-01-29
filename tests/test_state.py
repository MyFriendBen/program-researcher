"""Tests for state models."""

from datetime import date

import pytest

from program_research_agent.state import (
    EligibilityCriterion,
    FieldMapping,
    HumanTestCase,
    ImpactLevel,
    IssueSeverity,
    JSONTestCase,
    JSONTestCaseExpectedResults,
    JSONTestCaseHousehold,
    JSONTestCaseMember,
    JSONTestCaseMemberInsurance,
    LinkCatalog,
    LinkCatalogEntry,
    LinkCategory,
    QAIssue,
    QAValidationResult,
    ResearchState,
    ScenarioStep,
    ScenarioSuite,
    WorkflowStatus,
)


class TestLinkCatalog:
    """Tests for LinkCatalog and LinkCatalogEntry."""

    def test_link_catalog_entry_creation(self):
        """Test creating a link catalog entry."""
        entry = LinkCatalogEntry(
            category=LinkCategory.LEGISLATION,
            title="7 U.S.C. § 612c",
            url="https://uscode.house.gov/view.xhtml?req=7+USC+612c",
            source_type="Federal Law",
            found_in="Provided",
            accessible=True,
        )

        assert entry.category == LinkCategory.LEGISLATION
        assert entry.title == "7 U.S.C. § 612c"
        assert entry.accessible is True

    def test_link_catalog_creation(self):
        """Test creating a link catalog."""
        catalog = LinkCatalog(
            program_name="CSFP",
            state_code="il",
            research_date=date.today(),
            sources_provided=2,
            links=[
                LinkCatalogEntry(
                    category=LinkCategory.OFFICIAL_PROGRAM,
                    title="USDA CSFP",
                    url="https://www.fns.usda.gov/csfp",
                    source_type="Federal Agency",
                    found_in="Provided",
                )
            ],
        )

        assert catalog.program_name == "CSFP"
        assert len(catalog.links) == 1


class TestEligibilityCriterion:
    """Tests for EligibilityCriterion model."""

    def test_criterion_with_fields(self):
        """Test criterion that can be evaluated."""
        criterion = EligibilityCriterion(
            criterion="Age must be 60 or older",
            source_reference="7 CFR 247.9(a)",
            screener_fields=["household_member.age"],
            evaluation_logic="member.age >= 60",
            impact=ImpactLevel.HIGH,
        )

        assert criterion.screener_fields is not None
        assert len(criterion.screener_fields) == 1

    def test_criterion_data_gap(self):
        """Test criterion that cannot be evaluated (data gap)."""
        criterion = EligibilityCriterion(
            criterion="Must not reside in institution",
            source_reference="State manual p.8",
            screener_fields=None,
            notes="No institutionalization field",
            impact=ImpactLevel.LOW,
        )

        assert criterion.screener_fields is None
        assert criterion.impact == ImpactLevel.LOW


class TestQAModels:
    """Tests for QA-related models."""

    def test_qa_issue_creation(self):
        """Test creating a QA issue."""
        issue = QAIssue(
            severity=IssueSeverity.CRITICAL,
            issue_type="missed_criterion",
            description="Income limit criterion not captured",
            location="criteria_can_evaluate",
            suggested_fix="Add income limit criterion",
        )

        assert issue.severity == IssueSeverity.CRITICAL
        assert issue.resolved is False

    def test_qa_validation_result(self):
        """Test QA validation result."""
        result = QAValidationResult(
            validation_type="research",
            overall_status="VALIDATED_WITH_CONCERNS",
            issues=[
                QAIssue(
                    severity=IssueSeverity.MINOR,
                    issue_type="unclear_source",
                    description="Source citation could be more specific",
                    location="criteria[0]",
                    suggested_fix="Add section number",
                )
            ],
            summary="1 minor issue found",
            recommendation="Proceed with caution",
        )

        assert result.overall_status == "VALIDATED_WITH_CONCERNS"
        assert len(result.issues) == 1


class TestTestCaseModels:
    """Tests for test case models."""

    def test_human_test_case_creation(self):
        """Test creating a human-readable test case."""
        tc = HumanTestCase(
            scenario_number=1,
            title="Clearly Eligible Senior",
            what_checking="Typical senior who should qualify",
            category="happy_path",
            expected_eligible=True,
            expected_amount=600,
            expected_time="15 minutes",
            steps=[
                ScenarioStep(
                    section="Location",
                    instructions=["Enter ZIP code `60601`", "Select county `Cook`"],
                )
            ],
            what_to_look_for=["CSFP should appear in results"],
            why_matters="Confirms program shows for typical applicant",
            zip_code="60601",
            county="Cook",
            household_size=1,
            household_assets=0,
            members_data=[
                {
                    "relationship": "headOfHousehold",
                    "birth_month": 3,
                    "birth_year": 1953,
                }
            ],
            citizenship_status="citizen",
        )

        assert tc.scenario_number == 1
        assert tc.expected_eligible is True
        assert len(tc.steps) == 1

    def test_json_test_case_creation(self):
        """Test creating a JSON test case."""
        member = JSONTestCaseMember(
            relationship="headOfHousehold",
            birth_month=3,
            birth_year=1953,
            age=72,
            insurance=JSONTestCaseMemberInsurance(none=True),
        )

        household = JSONTestCaseHousehold(
            household_size=1,
            zip_code="60601",
            county="Cook",
            household_assets=0,
            agree_to_terms_of_service=True,
            is_13_or_older=True,
            members=[member],
        )

        json_tc = JSONTestCase(
            test_id="il_csfp_01",
            white_label="il",
            program_name="il_csfp",
            household=household,
            expected_results=JSONTestCaseExpectedResults(
                eligibility=True,
                benefit_amount=600,
            ),
        )

        assert json_tc.test_id == "il_csfp_01"
        assert len(json_tc.household.members) == 1


class TestResearchState:
    """Tests for the main ResearchState."""

    def test_initial_state(self):
        """Test creating initial research state."""
        state = ResearchState(
            program_name="CSFP",
            state_code="il",
            white_label="il",
            source_urls=["https://www.fns.usda.gov/csfp"],
        )

        assert state.program_name == "CSFP"
        assert state.status == WorkflowStatus.IN_PROGRESS
        assert state.research_iteration == 0
        assert state.max_iterations == 3

    def test_state_with_all_fields(self):
        """Test state with all optional fields populated."""
        state = ResearchState(
            program_name="CSFP",
            state_code="il",
            white_label="il",
            source_urls=["https://example.com"],
            link_catalog=LinkCatalog(
                program_name="CSFP",
                state_code="il",
                research_date=date.today(),
                sources_provided=1,
            ),
            field_mapping=FieldMapping(program_name="CSFP"),
            test_suite=ScenarioSuite(
                program_name="CSFP",
                white_label="il",
            ),
            status=WorkflowStatus.COMPLETED,
            messages=["Done"],
        )

        assert state.status == WorkflowStatus.COMPLETED
        assert state.link_catalog is not None
        assert state.field_mapping is not None
