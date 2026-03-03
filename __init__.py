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
    # Relative imports work when imported as part of the 'program_research_agent' package.
    # They may fail when pytest imports this __init__.py standalone for package discovery;
    # in that case we suppress the error — tests import directly from submodules.
    from .state import (
        EligibilityCriterion,
        FieldMapping,
        HumanTestCase,
        LinkCatalog,
        LinkCatalogEntry,
        QAIssue,
        QAValidationResult,
        ResearchState,
        ScenarioSuite,
    )
except ImportError:
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
]
