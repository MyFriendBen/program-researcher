#!/usr/bin/env python3
"""
Example: Research Illinois CSFP Program

This script demonstrates how to use the Program Research Agent
to research the Commodity Supplemental Food Program (CSFP) in Illinois.

Usage:
    python examples/research_csfp.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from program_research_agent.graph import run_research
from program_research_agent.state import WorkflowStatus


async def main():
    """Research the Illinois CSFP program."""

    # Check for API key
    if not os.getenv("RESEARCH_AGENT_ANTHROPIC_API_KEY"):
        print("Error: RESEARCH_AGENT_ANTHROPIC_API_KEY environment variable not set")
        print("Set it with: export RESEARCH_AGENT_ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    print("=" * 60)
    print("Program Research Agent - Illinois CSFP Example")
    print("=" * 60)
    print()

    # Run research
    state = await run_research(
        program_name="CSFP",
        state_code="il",
        white_label="il",
        source_urls=[
            "https://www.fns.usda.gov/csfp/commodity-supplemental-food-program",
            "https://www.dhs.state.il.us/page.aspx?item=30513",
        ],
        max_iterations=3,
    )

    # Print results summary
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print()

    print(f"Status: {state.status.value}")
    print()

    if state.link_catalog:
        print(f"Links discovered: {len(state.link_catalog.links)}")
        print("  Categories:")
        categories = {}
        for link in state.link_catalog.links:
            cat = link.category.value if hasattr(link.category, "value") else link.category
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in sorted(categories.items()):
            print(f"    - {cat}: {count}")
        print()

    if state.field_mapping:
        print(f"Eligibility criteria found:")
        print(f"  - Can evaluate: {len(state.field_mapping.criteria_can_evaluate)}")
        print(f"  - Data gaps: {len(state.field_mapping.criteria_cannot_evaluate)}")
        print()

        if state.field_mapping.criteria_can_evaluate:
            print("  Evaluable criteria:")
            for criterion in state.field_mapping.criteria_can_evaluate[:5]:
                print(f"    • {criterion.criterion[:60]}...")
        print()

    if state.test_suite:
        print(f"Test scenarios generated: {len(state.test_suite.test_cases)}")
        print("  Categories:")
        categories = {}
        for tc in state.test_suite.test_cases:
            categories[tc.category] = categories.get(tc.category, 0) + 1
        for cat, count in sorted(categories.items()):
            print(f"    - {cat}: {count}")
        print()

    print(f"JSON test cases: {len(state.json_test_cases)}")
    print()

    print("QA iterations:")
    print(f"  - Research: {state.research_iteration}")
    print(f"  - Test cases: {state.test_case_iteration}")
    print(f"  - JSON: {state.json_iteration}")
    print()

    if state.linear_ticket_url:
        print(f"Linear ticket: {state.linear_ticket_url}")
    elif state.linear_ticket:
        print("Linear ticket content generated (API not configured)")
    print()

    # Print last few workflow messages
    if state.messages:
        print("Last workflow messages:")
        for msg in state.messages[-5:]:
            print(f"  {msg}")
    print()

    if state.status == WorkflowStatus.COMPLETED:
        print("✅ Research completed successfully!")
    else:
        print(f"⚠️ Research ended with status: {state.status.value}")

    return state


if __name__ == "__main__":
    asyncio.run(main())
