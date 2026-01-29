"""
Node: Read Screener Fields

Step 2 of the QA process - read the current screener data model.
"""

from ..state import ResearchState
from ..tools.screener_fields import get_screener_fields


async def read_screener_fields_node(state: ResearchState) -> dict:
    """
    Read screener field definitions from the codebase.

    This node reads:
    - Django models (benefits-be/screener/models.py)
    - TypeScript types (benefits-fe/src/Types/FormData.ts)

    And extracts all available fields for eligibility calculations.
    """
    messages = list(state.messages)
    messages.append("Reading screener field definitions from codebase...")

    try:
        catalog = get_screener_fields()

        # Log what we found
        total_fields = (
            len(catalog.screen_fields)
            + len(catalog.household_member_fields)
            + len(catalog.income_fields)
            + len(catalog.expense_fields)
            + len(catalog.insurance_fields)
        )

        messages.append(f"Found {total_fields} screener fields:")
        messages.append(f"  - Screen (household): {len(catalog.screen_fields)} fields")
        messages.append(f"  - HouseholdMember: {len(catalog.household_member_fields)} fields")
        messages.append(f"  - IncomeStream: {len(catalog.income_fields)} fields")
        messages.append(f"  - Expense: {len(catalog.expense_fields)} fields")
        messages.append(f"  - Insurance: {len(catalog.insurance_fields)} fields")
        messages.append(f"  - Helper methods: {len(catalog.helper_methods)} methods")

        return {
            "screener_fields": catalog,
            "messages": messages,
        }

    except Exception as e:
        messages.append(f"Error reading screener fields: {e}")
        messages.append("Continuing with limited field information...")

        # Return empty catalog so workflow can continue
        from ..state import ScreenerFieldCatalog
        return {
            "screener_fields": ScreenerFieldCatalog(),
            "messages": messages,
        }
