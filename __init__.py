"""
Program Research Agent

A LangGraph-based multi-agent system for researching benefit programs,
validating eligibility criteria, generating test cases, and creating
implementation tickets.

Usage:
    research-program --program "CSFP" --state "il" --white-label "il" \
        --source-url "https://example.com/csfp"
"""

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
