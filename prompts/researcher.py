"""
Prompts for the Researcher Agent.

The researcher agent handles:
- Link discovery and cataloging
- Eligibility criteria extraction
- Field mapping to screener
- Test case generation
- JSON conversion
"""

SYSTEM_PROMPT = """You are a benefits program researcher specializing in government assistance programs. Your role is to thoroughly research benefit programs using official sources, extract precise eligibility criteria, and generate comprehensive test scenarios.

## Core Principles

1. **Accuracy First**: Always cite specific sections (e.g., "7 CFR 247.9(a)", "42 U.S.C. § 1396"). Never make assumptions about eligibility criteria.

2. **Use Official Sources**: Prioritize federal and state government sources (.gov domains), official regulations (CFR, state admin codes), and legislation (U.S. Code, state statutes).

3. **Be Thorough**: Extract ALL eligibility criteria, not just the obvious ones. Include income limits, categorical requirements, geographic restrictions, and exclusions.

4. **Be Precise**: Use exact numeric thresholds from legislation. If income limit is 130% FPL, don't round or approximate.

5. **Document Everything**: Every claim should have a source citation. If you can't find a source, say so.

## Output Standards

- Use markdown formatting for structured output
- Include tables where appropriate
- Always include source citations with URLs
- Use consistent terminology matching the screener field names
"""

GATHER_LINKS_PROMPT = """## Task: Gather Documentation Links

Research the benefit program and create a comprehensive catalog of all relevant documentation.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}
- **Source URLs Provided**:
{source_urls}

### Instructions

1. **Fetch each provided source URL** and read the full content
2. **Extract all hyperlinks** found within each source document
3. **Identify legislative citations** in the text that may not be hyperlinked:
   - U.S. Code citations (e.g., "42 U.S.C. § 1396")
   - CFR references (e.g., "7 CFR Part 273")
   - Public Law numbers (e.g., "P.L. 117-169")
   - State statute references (e.g., "C.R.S. 26-2-104")
4. **Convert text citations to URLs** where possible using official sources:
   - U.S. Code: https://uscode.house.gov/
   - CFR: https://www.ecfr.gov/
   - Congress.gov for Public Laws
5. **Categorize each link** as:
   - Official Program: Government agency program pages
   - Legislation: Federal or state laws
   - Regulation: CFR or state administrative codes
   - Application: Online portals and forms
   - Research: Policy briefs, calculators
   - Navigator: Local assistance resources
6. **Verify accessibility** of each link

### Output Format

Return a JSON object with this structure:
```json
{{
  "program_name": "{program_name}",
  "state_code": "{state_code}",
  "research_date": "YYYY-MM-DD",
  "sources_provided": <count>,
  "links": [
    {{
      "category": "Official Program|Legislation|Regulation|Application|Research|Navigator",
      "title": "Descriptive title including citation if applicable",
      "url": "https://...",
      "source_type": "Federal Agency|State Agency|Federal Law|Federal Regulation|etc.",
      "found_in": "Provided|Referenced in [source name]",
      "accessible": true|false,
      "content_summary": "Brief 1-2 sentence summary"
    }}
  ]
}}
```

Be thorough - a typical program should have 10-30 relevant links including legislation, regulations, and agency resources.
"""

EXTRACT_CRITERIA_PROMPT = """## Task: Extract Eligibility Criteria and Map to Screener Fields

Analyze the program documentation to extract all eligibility criteria and map them to available screener fields.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}

### Link Catalog
{link_catalog}

### Available Screener Fields
{screener_fields}

### Instructions

1. **Review each source document** from the link catalog
2. **Extract ALL eligibility criteria**, including:
   - Income limits (gross, net, as % of FPL)
   - Asset/resource limits
   - Age requirements (minimum, maximum, ranges)
   - Categorical requirements (children, elderly, disabled, pregnant)
   - Citizenship/immigration status requirements
   - Residency requirements (state, county)
   - Program-specific requirements (work requirements, prior benefit receipt)
   - Exclusion criteria (who is NOT eligible)

3. **For each criterion, determine**:
   - Can we evaluate it with current screener fields?
   - If yes, which field(s) and what logic?
   - If no, why not and what's the impact?

4. **Cite the specific source** for each criterion (section, paragraph, URL)

### Output Format

Return a JSON object with this structure:
```json
{{
  "program_name": "{program_name}",
  "criteria_can_evaluate": [
    {{
      "criterion": "Income must be at or below 130% of the Federal Poverty Level",
      "source_reference": "7 CFR 247.9(a)(1)",
      "source_url": "https://www.ecfr.gov/...",
      "screener_fields": ["income (all types)", "household_size"],
      "evaluation_logic": "calc_gross_income('yearly') <= FPL_130_PERCENT[household_size]",
      "notes": "Uses household gross income, FPL values from program year",
      "impact": "High"
    }}
  ],
  "criteria_cannot_evaluate": [
    {{
      "criterion": "Must not reside in an institution",
      "source_reference": "State Policy Manual Section 4.2",
      "source_url": "https://...",
      "screener_fields": null,
      "evaluation_logic": null,
      "notes": "No institutionalization field in screener",
      "impact": "Low"
    }}
  ],
  "summary": "X of Y criteria can be evaluated with current screener fields...",
  "recommendations": [
    "Consider adding field X to address gap Y",
    "Gap Z is acceptable - rare edge case"
  ]
}}
```

Impact levels:
- **High**: Core requirement affecting most applicants
- **Medium**: Affects meaningful subset of applicants
- **Low**: Edge case or rarely applicable
"""

GENERATE_TEST_CASES_PROMPT = """## Task: Generate Human-Readable Test Scenarios

Create comprehensive test scenarios for manual QA testing of the program implementation.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}
- **White Label**: {white_label}

### Eligibility Criteria (that can be evaluated)
{criteria_can_evaluate}

### Available Screener Fields
{screener_fields}

### Instructions

Generate **10-15 test scenarios** covering:

1. **Happy Path** (2 scenarios)
   - Clearly eligible household
   - Minimally eligible (just meets all criteria)

2. **Income Thresholds** (3-4 scenarios)
   - Income just below limit (eligible)
   - Income exactly at limit (eligible)
   - Income just above limit (not eligible)
   - Multiple income sources if relevant

3. **Age Thresholds** (2-3 scenarios) - if program has age requirements
   - Age just below minimum (not eligible)
   - Age exactly at minimum (eligible)
   - Age above minimum (eligible)

4. **Geographic** (1-2 scenarios) - if program has geographic limits
   - Eligible location
   - Ineligible location

5. **Exclusions** (2 scenarios)
   - Already has the benefit
   - Citizenship/status restriction (if applicable)

6. **Multi-Member Households** (2-3 scenarios)
   - Mixed household (some members eligible, some not)
   - All members eligible
   - No members eligible

### Output Format

Return a JSON object:
```json
{{
  "program_name": "{program_name}",
  "white_label": "{white_label}",
  "test_cases": [
    {{
      "scenario_number": 1,
      "title": "Clearly Eligible Senior",
      "what_checking": "A typical senior who should easily qualify for the program",
      "category": "happy_path",
      "expected_eligible": true,
      "expected_amount": 600,
      "expected_time": "15 minutes",
      "steps": [
        {{
          "section": "Location",
          "instructions": ["Enter ZIP code `60601`", "Select county `Cook`"]
        }},
        {{
          "section": "Household",
          "instructions": ["Number of people: `1`"]
        }},
        {{
          "section": "Person 1",
          "instructions": [
            "Birth month/year: `March 1953` (age 72)",
            "Relationship: Select `Head of Household`",
            "Income: `$800` per month, select `Social Security` as type"
          ]
        }},
        {{
          "section": "Current Benefits",
          "instructions": ["Leave {program_name} unchecked"]
        }},
        {{
          "section": "Citizenship",
          "instructions": ["Select `U.S. Citizen`"]
        }}
      ],
      "what_to_look_for": [
        "\"{program_name}\" should appear in results",
        "Value should show $600/year",
        "Application time should show 15 minutes"
      ],
      "why_matters": "Confirms the program shows up for a typical eligible applicant",
      "zip_code": "60601",
      "county": "Cook",
      "household_size": 1,
      "household_assets": 0,
      "members_data": [
        {{
          "relationship": "headOfHousehold",
          "birth_month": 3,
          "birth_year": 1953,
          "has_income": true,
          "income": {{
            "sSRetirement": 800,
            "income_frequency": "monthly"
          }},
          "insurance": {{"none": true}}
        }}
      ],
      "current_benefits": {{}},
      "citizenship_status": "citizen"
    }}
  ],
  "coverage_summary": "15 scenarios covering income thresholds, age requirements, geographic restrictions, and multi-member households"
}}
```

### Important Notes

- Use realistic values based on current FPL and program thresholds
- Calculate birth years from current date to get exact ages
- Include exact numeric values from the eligibility criteria
- Each scenario must have complete data for JSON conversion
- Test boundary conditions precisely (e.g., if 130% FPL for 1 person is $1,580/month, test $1,579 and $1,581)
"""

CONVERT_TO_JSON_PROMPT = """## Task: Convert Test Cases to JSON Schema Format

Convert the human-readable test cases to the pre_validation_schema.json format.

### Program Information
- **Program Name**: {program_name}
- **White Label**: {white_label}

### Human Test Cases
{test_cases}

### JSON Schema Reference
{json_schema}

### Instructions

Convert each test case to a JSON object matching the pre_validation_schema.json structure:

1. **test_id**: Format as "{white_label}_{program_name}_{scenario_number}" (e.g., "il_csfp_01")
2. **white_label**: Use "{white_label}"
3. **program_name**: Use the program's internal identifier
4. **household**: Convert the test case data:
   - Calculate `age` from birth_month and birth_year (current date: {current_date})
   - Map income fields to correct property names (sSRetirement, wages, etc.)
   - Include all required fields (agree_to_terms_of_service, is_13_or_older)
5. **expected_results**:
   - eligibility: boolean matching expected_eligible
   - benefit_amount: from expected_amount (if applicable)

### Output Format

Return a JSON array:
```json
[
  {{
    "test_id": "il_csfp_01",
    "white_label": "il",
    "program_name": "il_csfp",
    "household": {{
      "household_size": 1,
      "zip_code": "60601",
      "county": "Cook",
      "household_assets": 0,
      "agree_to_terms_of_service": true,
      "is_13_or_older": true,
      "members": [
        {{
          "relationship": "headOfHousehold",
          "birth_month": 3,
          "birth_year": 1953,
          "age": 72,
          "has_income": true,
          "income": {{
            "sSRetirement": 800,
            "income_frequency": "monthly"
          }},
          "insurance": {{
            "none": true
          }}
        }}
      ]
    }},
    "expected_results": {{
      "eligibility": true,
      "benefit_amount": 600
    }}
  }}
]
```

Ensure all JSON is valid and matches the schema exactly.
"""

FIX_ISSUES_PROMPT = """## Task: Address QA Issues

The QA agent has identified issues that need to be fixed.

### Current Output
{current_output}

### QA Issues Found
{qa_issues}

### Instructions

For each issue:
1. Understand what's wrong and why
2. Make the specific correction needed
3. Ensure the fix doesn't introduce new issues
4. Maintain all other content unchanged

### Output

Return the corrected version of the output in the same format, with all issues addressed.

If an issue cannot be fully addressed, note why in a `_fix_notes` field.
"""

GENERATE_SINGLE_TEST_CASE_PROMPT = """## Task: Generate a Single Test Scenario

Create ONE test scenario for the specified category.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}
- **White Label**: {white_label}

### Eligibility Criteria (that can be evaluated)
{criteria_can_evaluate}

### Test Case Requirements
- **Category**: {category}
- **Scenario Number**: {scenario_number}
- **Description**: {category_description}

### Previously Generated Scenarios
{previous_scenarios}

### Output Format

Return a JSON object for this SINGLE test case:
```json
{{
  "scenario_number": {scenario_number},
  "title": "Descriptive Title",
  "what_checking": "What this specific test validates",
  "category": "{category}",
  "expected_eligible": true|false,
  "expected_amount": null or number,
  "expected_time": "15 minutes",
  "steps": [
    {{
      "section": "Location",
      "instructions": ["Enter ZIP code `XXXXX`", "Select county `County Name`"]
    }},
    {{
      "section": "Household",
      "instructions": ["Number of people: `X`"]
    }},
    {{
      "section": "Person 1",
      "instructions": ["Birth month/year: `Month Year` (age XX)", "..."]
    }}
  ],
  "what_to_look_for": ["Expected result 1", "Expected result 2"],
  "why_matters": "Why this test is important",
  "zip_code": "XXXXX",
  "county": "County Name",
  "household_size": 1,
  "household_assets": 0,
  "members_data": [
    {{
      "relationship": "headOfHousehold",
      "birth_month": 3,
      "birth_year": 1960,
      "has_income": true,
      "income": {{
        "sSRetirement": 800,
        "income_frequency": "monthly"
      }},
      "insurance": {{"none": true}}
    }}
  ],
  "current_benefits": {{}},
  "citizenship_status": "citizen"
}}
```

### Important
- Return ONLY the JSON object for this single test case
- Use realistic values based on current FPL and program thresholds
- Calculate birth years from current date to get exact ages
- Ensure the scenario is DIFFERENT from previously generated ones
- Make sure to test the specific aspect described in the category description
"""

# Test case categories with descriptions
TEST_CASE_CATEGORIES = [
    ("happy_path", "Clearly eligible household - typical applicant who easily qualifies"),
    ("happy_path", "Minimally eligible - just barely meets all criteria"),
    ("income_threshold", "Income just below limit - should be eligible"),
    ("income_threshold", "Income exactly at limit - should be eligible"),
    ("income_threshold", "Income just above limit - should NOT be eligible"),
    ("age_threshold", "Age exactly at minimum requirement - should be eligible"),
    ("age_threshold", "Age just below minimum - should NOT be eligible"),
    ("age_threshold", "Age well above minimum - should be eligible"),
    ("geographic", "Eligible location within service area"),
    ("exclusion", "Already receives the benefit - should show as ineligible or different message"),
    ("exclusion", "Excluded due to other program participation (e.g., SNAP for CSFP)"),
    ("multi_member", "Mixed household - some members eligible, some not"),
    ("multi_member", "Multiple eligible members in same household"),
    ("edge_case", "Boundary condition or unusual but valid scenario"),
]

# Dictionary for easy access
RESEARCHER_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "gather_links": GATHER_LINKS_PROMPT,
    "extract_criteria": EXTRACT_CRITERIA_PROMPT,
    "generate_test_cases": GENERATE_TEST_CASES_PROMPT,
    "generate_single_test_case": GENERATE_SINGLE_TEST_CASE_PROMPT,
    "convert_to_json": CONVERT_TO_JSON_PROMPT,
    "fix_issues": FIX_ISSUES_PROMPT,
    "test_case_categories": TEST_CASE_CATEGORIES,
}
