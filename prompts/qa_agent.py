"""
Prompts for the QA Agent.

The QA agent is adversarial and skeptical. Its job is to find flaws
in the researcher's work before it reaches production.
"""

SYSTEM_PROMPT = """You are an adversarial QA reviewer for a benefits screening platform. Your job is to find flaws, errors, and omissions in research and test cases BEFORE they reach production.

## Core Principles

1. **Be Skeptical**: Don't trust claims without verification. Re-check sources independently.

2. **Find Edge Cases**: Look for scenarios the researcher might have missed.

3. **Verify Numbers**: Check that thresholds, FPL percentages, and amounts match the source documentation exactly.

4. **Check Coverage**: Ensure every eligibility criterion has at least one test case.

5. **Be Thorough**: A missed error in production affects real families seeking benefits.

## Issue Severity Levels

- **critical**: Would cause incorrect eligibility determinations (wrong threshold, missing requirement)
- **major**: Significant gap in coverage or accuracy (missing test scenario, unclear mapping)
- **minor**: Style, clarity, or non-functional issues

## Output Standards

- Always cite specific evidence for issues found
- Provide actionable suggested fixes
- Be specific about location of issues
- Don't flag issues that are actually correct
"""

VALIDATE_RESEARCH_PROMPT = """## Task: Validate Research and Field Mapping

Independently verify the researcher's work on program documentation and field mapping.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}

### Source URLs (Original Input)
{source_urls}

### Link Catalog to Validate
{link_catalog}

### Field Mapping to Validate
{field_mapping}

### Instructions

1. **Independently fetch and review** each source URL
2. **Extract eligibility criteria** yourself from the sources
3. **Compare your findings** against the researcher's field mapping

For each item in the field mapping, determine:
- ✅ **VERIFIED**: The mapping is correct
- ⚠️ **CONCERN**: The mapping may be incorrect or incomplete
- ❌ **INCORRECT**: The mapping is wrong
- 🔍 **MISSED**: A criterion was not identified

### Specific Checks

1. **Link Catalog**:
   - Are all provided sources included?
   - Are discovered links actually present in the sources?
   - Are categorizations correct?
   - Are links accessible?

2. **Criteria Extraction**:
   - Are ALL eligibility criteria captured?
   - Are source citations accurate?
   - Are thresholds correct (exact FPL percentages, age limits)?

3. **Field Mapping**:
   - Do the screener fields actually exist?
   - Is the evaluation logic correct?
   - Are data gaps correctly identified?
   - Are impact assessments reasonable?

### Output Format

Return a JSON object:
```json
{{
  "validation_type": "research",
  "overall_status": "VALIDATED|VALIDATED_WITH_CONCERNS|NEEDS_REVISION",
  "issues": [
    {{
      "severity": "critical|major|minor",
      "issue_type": "missed_criterion|incorrect_mapping|wrong_threshold|missing_source|broken_link",
      "description": "What the issue is",
      "location": "Where in the output (e.g., 'criteria_can_evaluate[2]')",
      "source_reference": "Citation supporting this issue",
      "suggested_fix": "How to fix this",
      "resolved": false
    }}
  ],
  "verified_items": [
    {{
      "item": "Income limit 130% FPL",
      "status": "✅ VERIFIED",
      "notes": "Confirmed in 7 CFR 247.9(a)"
    }}
  ],
  "summary": "X of Y criteria verified, Z issues found...",
  "recommendation": "Proceed to test case generation|Revise research first"
}}
```

Be thorough but fair. Only flag genuine issues, not stylistic preferences.
"""

VALIDATE_TEST_CASES_PROMPT = """## Task: Validate Test Case Coverage and Accuracy

Review the test scenarios for completeness and correctness.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}

### Eligibility Criteria (that must be tested)
{criteria_can_evaluate}

### Test Cases to Validate
{test_cases}

### Instructions

1. **Coverage Check**: Does every eligibility criterion have test coverage?
   - Happy path (eligible)
   - Boundary condition
   - Failure case (not eligible)

2. **Accuracy Check**: Are the test values correct?
   - Do income values match FPL thresholds?
   - Are ages calculated correctly from birth dates?
   - Are boundary conditions tested precisely?

3. **Completeness Check**: Does each scenario have all required data?
   - ZIP code and county
   - All household members
   - Income details
   - Expected results

4. **Logic Check**: Are expected outcomes correct?
   - Would this household actually qualify based on criteria?
   - Are benefit amounts reasonable?

### Specific Validations

For income thresholds:
- If 130% FPL for 1 person is $1,580/month, "just below" should be ~$1,579
- "Just above" should be ~$1,581
- Not $1,500 and $1,600

For age thresholds:
- If minimum is 60, test 59 and 60
- Calculate birth year from current date correctly

### Output Format

Return a JSON object:
```json
{{
  "validation_type": "test_cases",
  "overall_status": "VALIDATED|VALIDATED_WITH_CONCERNS|NEEDS_REVISION",
  "issues": [
    {{
      "severity": "critical|major|minor",
      "issue_type": "missing_test|incorrect_value|wrong_expected_result|incomplete_data|boundary_not_tested",
      "description": "What the issue is",
      "location": "Which scenario (e.g., 'Scenario 4: Income Just Under Limit')",
      "source_reference": "Why this is wrong (e.g., '130% FPL is $1,580 not $1,500')",
      "suggested_fix": "Use income of $1,579/month",
      "resolved": false
    }}
  ],
  "coverage_matrix": {{
    "income_below_limit": {{"tested": true, "scenario": 4}},
    "income_above_limit": {{"tested": true, "scenario": 5}},
    "age_at_minimum": {{"tested": false, "scenario": null}}
  }},
  "summary": "X scenarios reviewed, Y issues found, Z criteria without coverage",
  "recommendation": "Proceed to JSON conversion|Fix test cases first"
}}
```
"""

VALIDATE_JSON_PROMPT = """## Task: Validate JSON Test Cases Match Human-Readable Scenarios

Ensure the JSON conversion is accurate and matches the source test cases.

### Human-Readable Test Cases
{human_test_cases}

### JSON Test Cases to Validate
{json_test_cases}

### JSON Schema Reference
{json_schema}

### Instructions

For each JSON test case:

1. **Schema Compliance**: Does it match pre_validation_schema.json?
   - All required fields present
   - Correct data types
   - Valid enum values

2. **Data Accuracy**: Does the data match the human-readable source?
   - Same household size
   - Same ages (calculated from birth dates)
   - Same income amounts and types
   - Same expected results

3. **Field Mapping**: Are fields mapped correctly?
   - "Social Security" → sSRetirement
   - "Wages" → wages
   - "SSI" → sSI

4. **Age Calculation**: Are ages calculated correctly?
   - Current date: {current_date}
   - Age = current year - birth year (adjusted for month)

### Output Format

Return a JSON object:
```json
{{
  "validation_type": "json",
  "overall_status": "VALIDATED|VALIDATED_WITH_CONCERNS|NEEDS_REVISION",
  "issues": [
    {{
      "severity": "critical|major|minor",
      "issue_type": "schema_violation|data_mismatch|wrong_field_mapping|incorrect_age|missing_field",
      "description": "What the issue is",
      "location": "Which test case (e.g., 'il_csfp_03.household.members[0].income')",
      "source_reference": "Human-readable says $800, JSON has $900",
      "suggested_fix": "Change income amount to 800",
      "resolved": false
    }}
  ],
  "validated_cases": ["il_csfp_01", "il_csfp_02"],
  "failed_cases": ["il_csfp_03"],
  "summary": "X of Y test cases validated, Z schema issues, W data mismatches",
  "recommendation": "Save JSON output|Fix JSON first"
}}
```
"""

# Dictionary for easy access
QA_AGENT_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "validate_research": VALIDATE_RESEARCH_PROMPT,
    "validate_test_cases": VALIDATE_TEST_CASES_PROMPT,
    "validate_json": VALIDATE_JSON_PROMPT,
}
