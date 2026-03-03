"""
Program Research Agent

A LangGraph-based multi-agent system for researching benefit programs,
validating eligibility criteria, generating test cases, and creating
implementation tickets.

Usage:
    research-program --program "CSFP" --state "il" --white-label "il" \
        --source-url "https://example.com/csfp"
"""

try:
    from .state import (
        EligibilityCriterion,
        FieldMapping,
        HumanTestCase,
        JSONTestCase,
        LinkCatalog,
        LinkCatalogEntry,
        QAIssue,
        QAValidationResult,
        ResearchState,
        ScenarioSuite,
    )
except ImportError:
    # Happens when pytest imports this file directly by path (the directory
    # name "program-researcher" has a hyphen so pytest can't resolve it as a
    # package). Tests import from program_research_agent.state directly, so
    # these convenience re-exports are not needed at test time.
    pass

__version__ = "0.1.0"

__all__ = [
    "ResearchState",
    "LinkCatalog",
    "LinkCatalogEntry",
    "EligibilityCriterion",
    "FieldMapping",
    "HumanTestCase",
    "ScenarioSuite",
    "QAIssue",
    "QAValidationResult",
    "JSONTestCase",
]
