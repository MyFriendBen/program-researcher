"""
Prompts for the Researcher Agent.

The researcher agent handles:
- Link discovery and cataloging
- Eligibility criteria extraction
- Field mapping to screener
- Test case generation
- JSON conversion
- Program configuration generation
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
2. **Prioritize finding application PDFs and forms** - these often contain detailed eligibility criteria not on main pages
   - Look for links containing: "application", "apply", "form", ".pdf", "eligibility"
   - Check "How to Apply" sections for linked documents
3. **Extract all hyperlinks** found within each source document
4. **Identify legislative citations** in the text that may not be hyperlinked:
   - U.S. Code citations (e.g., "42 U.S.C. § 1396")
   - CFR references (e.g., "7 CFR Part 273")
   - Public Law numbers (e.g., "P.L. 117-169")
   - State statute references (e.g., "C.R.S. 26-2-104")
5. **Convert text citations to URLs** where possible using official sources:
   - U.S. Code: https://uscode.house.gov/
   - CFR: https://www.ecfr.gov/
   - Congress.gov for Public Laws
6. **Categorize each link** as:
   - Official Program: Government agency program pages
   - Legislation: Federal or state laws
   - Regulation: CFR or state administrative codes
   - Application: Online portals and forms
   - Research: Policy briefs, calculators
   - Navigator: Local assistance resources
7. **Verify accessibility** of each link

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

1. **Review each source document** from the link catalog, **ESPECIALLY application PDFs and forms**
   - Application PDFs often contain detailed eligibility requirements not on main website
   - Look for attached documents, linked PDFs, and application forms
   - **CRITICAL: For PDF URLs (.pdf files), you MUST use WebFetch tool to read them**
     - PDFs require vision capabilities to preserve structure (headings, bullets, emphasis)
     - WebFetch will automatically convert PDFs to images and use vision to extract content
     - When prompted, include the full PDF URL and request: "Extract all eligibility criteria, asset limits, income thresholds, preference criteria, and required documents from this PDF. Pay special attention to section headings in ALL CAPS and dollar amounts."

2. **Extract ALL eligibility criteria**, including:
   - Income limits (gross, net, as % of FPL or AMI)
   - **Asset/resource limits** (CRITICAL: look for specific dollar amounts, especially in application PDFs)
     - Liquid asset limits (cash, savings, checking accounts)
     - Age-based exceptions (e.g., "higher limit if all members 62+")
     - Asset types included/excluded
     - **For PDFs: Use WebFetch to search for sections titled "ASSET", "ASSETS", or "RESOURCES"**
   - Age requirements (minimum, maximum, ranges)
   - Categorical requirements (children, elderly, disabled, pregnant)
   - Citizenship/immigration status requirements (be specific - if source says "NA" or unclear, note that)
   - Residency requirements (state, county, minimum duration)
   - **Preference/priority criteria** (e.g., "preference for households with children")
     - **For PDFs: Use WebFetch to search for "PREFERENCE POINTS" or "PRIORITY" sections**
   - **Screening/administrative requirements** (credit checks, background checks, landlord references)
   - Program-specific requirements (work requirements, prior benefit receipt)
   - Exclusion criteria (who is NOT eligible)

   **Special Instructions for PDF Documents**:
   When you encounter a PDF URL (ending in .pdf):
   - You MUST use WebFetch tool to read it (WebFetch has vision capabilities for PDFs)
   - PDFs contain structure (headings, bullets, tables) that is lost in text-only extraction
   - In your WebFetch prompt, ask to:
     * "Identify and extract content from sections with ALL CAPS headings like 'ASSET', 'INCOME', 'PREFERENCE POINTS'"
     * "Extract all dollar amounts, percentages, and numeric thresholds"
     * "Preserve bullet point lists and structured criteria"
     * "Note any emphasized or bold values"
   - After WebFetch returns content, look for specific patterns:
     * "may not exceed $XX,XXX" = asset limit
     * "XX points" = preference criteria
     * "XX% AMI" or "XX% FPL" = income threshold

3. **For each criterion, determine**:
   - Can we evaluate it with current screener fields?
   - If yes, which field(s) and what logic?
   - If no, why not and what's the impact?

4. **Cite the specific source** for each criterion (section, paragraph, URL, page number if PDF)

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

### Current Date
Today is **{current_date}** (year: {current_year}). Use this to calculate all birth years and ages.

### Age Calculation Rule
To make a person age X: birth_year = {current_year} - X (adjust by 1 if their birth_month hasn't passed yet this year).
Example: a 65-year-old born in March when today is February 2026 → birth_year = 2026 - 65 - 1 = 1960, birth_month = 3.

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
      "birth_year": 1961,
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
- **CRITICAL**: birth_year values MUST be calculated from the current year ({current_year}), not guessed
- Use realistic values based on current FPL and program thresholds
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

GENERATE_PROGRAM_CONFIG_PROMPT = """## Task: Generate Program Configuration JSON

Generate a Django admin import configuration file for this benefit program using the research data provided below.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}
- **White Label**: {white_label}

### Research Context

The following research has been completed for this program. Use this data to populate the configuration fields:

{research_context}

### Instructions

**CRITICAL**: Use the research context above to extract:
1. **Official program name** from source documentation (not abbreviations)
2. **Comprehensive description** from program overviews and eligibility summaries
3. **Application link** from "Application" category links in sources
4. **Learn more link** from official program pages
5. **Legal status requirements** from eligibility criteria (if source says "NA" or unclear, do NOT add requirements)
6. **Required documents** from application materials and eligibility sources
7. **Application time estimate** from sources OR by analyzing application form complexity
8. **Benefit value estimate** by calculating from benefit descriptions and program rules
9. **Asset limits** from eligibility criteria (especially in application PDFs)
10. **Preference criteria** from program documentation (e.g., households with children)

Generate a JSON configuration matching this format:

```json
{{
  "white_label": {{
    "code": "{white_label}"
  }},
  "program_category": {{
    "external_name": "<whitelabel>_<category>"
  }},
  "program": {{
    "name_abbreviated": "{white_label}_{program_name}",
    "year": "2025",
    "legal_status_required": ["citizen", "refugee", ...],
    "name": "Full Program Name",
    "description": "Comprehensive description of the program, what it provides, and who it serves. Include any work requirements or special rules.",
    "description_short": "Brief one-line description",
    "learn_more_link": "https://official.gov/program",
    "apply_button_link": "https://apply.here/",
    "apply_button_description": "Apply for [Program]",
    "estimated_application_time": "30 - 60 minutes",
    "estimated_delivery_time": "30 days",
    "estimated_value": "",
    "website_description": "Short description for website display"
  }},
  "documents": [
    {{
      "external_name": "{white_label}_home",
      "text": "Proof of home address (ex: lease, utility bill)",
      "link_url": "",
      "link_text": ""
    }},
    {{
      "external_name": "id_proof",
      "text": "Proof of identity",
      "link_url": "",
      "link_text": ""
    }}
  ],
  "navigators": []
}}
```

### Field-by-Field Instructions

**program_category.external_name**:
- Determine category from program type:
  - Food programs → "{white_label}_food"
  - Healthcare/Medicaid → "{white_label}_healthcare"
  - Tax credits → "{white_label}_tax"
  - Housing → "{white_label}_housing"
  - Childcare → "{white_label}_childcare"
  - Cash assistance → "{white_label}_cash"

**program.legal_status_required**:
- Extract from eligibility criteria
- Common values: ["citizen", "gc_5plus", "gc_5less", "refugee", "otherWithWorkPermission", "non_citizen"]
- If unclear, use: ["citizen"]

**program.name**:
- Use official program name with acronym from research sources
- Example: "Supplemental Nutrition Assistance Program (SNAP)"
- NOT abbreviations like "SNAP" or "Snap" alone
- Extract from program overview or source titles

**program.description**:
- Write 2 concise paragraphs (100-150 words total) at 8th grade reading level:
  1. **What it provides**: Clear, simple explanation of the benefit (e.g., "monthly food packages", "help paying for healthcare")
  2. **Who can get it**: Basic eligibility in plain language (e.g., "seniors age 60 or older with low income")
- Keep sentences short and direct
- Avoid jargon and technical terms
- Include specific benefit amounts if available (e.g., "$60/month in groceries")
- Mention any important rules briefly (e.g., "work requirements may apply")
- Use information from eligibility criteria but simplify for general audience
- Think: someone skimming quickly needs to understand the basics

**program.description_short**:
- One-line description (5-10 words)
- Extract key benefit from description
- Example: "Monthly food packages for eligible seniors"

**program.learn_more_link**:
- Use the primary official source URL (usually .gov domain)
- Look for "Official Program" links in research sources

**program.apply_button_link**:
- Search for links with "Application" category in research
- Look for URLs containing keywords: apply, application, enroll, register
- Check source documentation for "How to Apply" or "Apply Now" links
- If no application link found, use learn_more_link

**program.apply_button_description**:
- Format: "Apply for [State] [Program]"
- Example: "Apply for IL CSFP"

**program.estimated_application_time**:
- **First priority**: Extract from CSV/research sources if available
- **Second priority**: If application PDF is available, estimate based on form complexity:
  - Count number of pages and fields in application
  - Simple forms (1-2 pages, <20 fields): "30 - 45 minutes"
  - Moderate forms (3-5 pages, 20-50 fields): "1 - 2 hours"
  - Complex forms (6+ pages, >50 fields, supporting docs): "2 - 3 hours"
- If no form available, use: "Varies"
- **IMPORTANT**: Do not underestimate - real applications take longer than reading them

**program.estimated_delivery_time**:
- Extract from sources if available (look for "processing time", "approval timeline")
- Check for phrases like "within X days", "X weeks", "X months"
- For housing programs: often "months to years" or "Varies based on unit availability"
- Leave empty if unknown

**program.estimated_value**:
- **CRITICAL**: Calculate or estimate monthly/annual benefit value when possible
- For housing programs: estimate rent reduction (e.g., "~$1000 per month" or "$12,000 per year")
  - Look for statements about "30% of income" or "affordable rent"
  - Compare to market rate if mentioned
- For food programs: look for package value or monthly amount
- For cash assistance: exact dollar amounts should be specified
- If benefit varies by household, note that (e.g., "Varies by household income and size")
- Leave empty ONLY if truly cannot be estimated from any source

**documents**:
- Generate common required documents based on program type
- Use these external_name patterns:
  - "{white_label}_home" → Proof of address
  - "{white_label}_ssn" → Social Security Number
  - "id_proof" → Proof of identity
  - "{white_label}_earned_income" → Proof of income
  - "{white_label}_expenses" → Proof of expenses
  - "{white_label}_us_status" → Proof of legal status
- Add program-specific documents if mentioned in sources

**navigators**:
- Leave as empty array []
- Human will add local contact information

### Output Requirements

1. Return ONLY valid JSON (no markdown, no explanation)
2. Ensure all required fields are present
3. Use empty string "" for unknown values, not null
4. Keep descriptions clear and non-technical
5. Double-check JSON syntax (commas, quotes, brackets)
6. **DO NOT use abbreviations or placeholder text** - use actual research data
7. **Descriptions must be complete** - not truncated or abbreviated

### Quality Checklist

Before returning, verify:
- [ ] Program name is official full name (not "Csfp" or "CSFP" alone)
- [ ] Description is 2 short paragraphs, 8th grade reading level, 100-150 words
- [ ] Description is clear and concise - no jargon or complex terms
- [ ] Application link extracted from sources (not generic or empty)
- [ ] Legal status requirements reflect eligibility criteria (do NOT add if source says "NA")
- [ ] Documents list is relevant to program type and extracted from application materials
- [ ] Application time is realistic (check form complexity, don't underestimate)
- [ ] Benefit value is calculated/estimated when possible (not left empty if calculable)
- [ ] Asset limits extracted if mentioned (especially check application PDFs)

Return the complete JSON configuration now:
"""

GENERATE_SOURCES_DOCUMENTATION_PROMPT = """## Task: Document Sources for Program Configuration

Create a human-readable markdown document that shows where EACH value in the program configuration came from.

### Program Information
- **Program Name**: {program_name}
- **State**: {state_code}
- **White Label**: {white_label}

### Program Configuration (Generated)
{program_config}

### Research Context
{research_context}

### Instructions

For EACH field in the program configuration JSON, document:
1. **The field name and its value**
2. **The source** (URL, PDF page, section name)
3. **How the value was determined** (extracted directly, calculated, inferred, default)
4. **Confidence level**: High (direct quote/extraction), Medium (paraphrased), Low (inferred/default)

### Output Format

Create a markdown document with this structure:

```markdown
# Source Documentation: {program_name}

**Date**: {date}
**State**: {state_code}
**White Label**: {white_label}

This document traces each value in the program configuration back to its source, ensuring transparency and verifiability.

---

## Program Identification

### white_label.code: "{value}"
- **Source**: System-assigned based on state
- **How Determined**: Standard state code mapping
- **Confidence**: High

### program_category.external_name: "{value}"
- **Source**: [Specific URL or document]
- **How Determined**: Categorized as {category} based on program type
- **Confidence**: High/Medium/Low
- **Quote/Evidence**: "Relevant text from source..."

---

## Program Metadata

### program.name_abbreviated: "{value}"
- **Source**: System-generated
- **How Determined**: Combined {white_label}_{program_name}
- **Confidence**: High

### program.year: "{value}"
- **Source**: Research date
- **How Determined**: Current program year based on research date
- **Confidence**: High

### program.name: "{value}"
- **Source**: [URL and section]
- **How Determined**: Extracted from official program page title/header
- **Confidence**: High
- **Quote/Evidence**: "Full program name as it appears..."

### program.legal_status_required: [{values}]
- **Source**: [URL, PDF page, or "Not explicitly stated"]
- **How Determined**: Extracted from eligibility criteria / Inferred from standard requirements / Not stated
- **Confidence**: High/Medium/Low
- **Quote/Evidence**: "Citizenship requirements..." OR "No explicit citizenship requirement stated"
- **Notes**: If this was inferred rather than documented, explain why

---

## Program Descriptions

### program.description: "{value}"
- **Source**: Synthesized from:
  - [URL 1]: Program overview
  - [URL 2]: Eligibility criteria
  - [PDF page X]: Application details
- **How Determined**: Combined information from multiple sources, simplified to 8th grade reading level
- **Confidence**: High
- **Key Facts Used**:
  - Benefit type: [from source X]
  - Income limits: [from source Y]
  - Special requirements: [from source Z]

### program.description_short: "{value}"
- **Source**: Derived from full description
- **How Determined**: Condensed key benefit statement
- **Confidence**: High

### program.website_description: "{value}"
- **Source**: [URL or derived]
- **How Determined**: Brief summary for website display
- **Confidence**: High

---

## Application Information

### program.learn_more_link: "{value}"
- **Source**: Primary official source
- **How Determined**: Selected main program page from research sources
- **Confidence**: High

### program.apply_button_link: "{value}"
- **Source**: [URL where application link was found]
- **How Determined**: Extracted from "How to Apply" / "Application" section
- **Confidence**: High/Medium
- **Notes**: Direct application link / PDF form / Portal URL

### program.apply_button_description: "{value}"
- **Source**: System-generated
- **How Determined**: Standard format "Apply for [State] [Program]"
- **Confidence**: High

---

## Time and Value Estimates

### program.estimated_application_time: "{value}"
- **Source**: [URL/PDF page OR "Estimated from form complexity"]
- **How Determined**:
  - Direct quote: "Application takes X minutes/hours"
  - OR Calculated from form: [X pages, Y fields, Z supporting documents]
- **Confidence**: High/Medium
- **Quote/Evidence**: "..." OR "Form analysis: X pages, Y fields = Z hour estimate"

### program.estimated_delivery_time: "{value}"
- **Source**: [URL/section OR "Not stated"]
- **How Determined**: Extracted from processing time information / Left as "Varies"
- **Confidence**: High/Medium/Low
- **Quote/Evidence**: "Processing takes..." OR "No delivery timeline stated"

### program.estimated_value: "{value}"
- **Source**: [URL/PDF OR "Calculated from benefit description"]
- **How Determined**:
  - Direct amount: "Recipients receive $X/month"
  - OR Calculated: "Rent reduced to 30% of income, market rent ~$Y, estimate ~$Z/month"
  - OR "Varies by household size and income"
- **Confidence**: High/Medium/Low
- **Quote/Evidence**: "..." OR "Calculation: [show math]"
- **Notes**: Explain why specific value vs "Varies"

---

## Required Documents

### documents[0]: {text}
- **external_name**: "{value}"
- **Source**: [Application PDF page X, section Y OR "Standard requirement for program type"]
- **How Determined**: Extracted from required documents list / Common requirement
- **Confidence**: High/Medium
- **Quote/Evidence**: "Applicants must provide..." OR "Standard ID requirement"

### documents[1]: {text}
- **external_name**: "{value}"
- **Source**: [specific source]
- **How Determined**: [method]
- **Confidence**: High/Medium/Low

[... repeat for each document ...]

---

## Warning Message

### warning_message: {value}
- **Source**: [URL/section OR null]
- **How Determined**: Extracted important warning/caveat / None found
- **Confidence**: High/Medium
- **Quote/Evidence**: "..." OR "No specific warnings noted in documentation"

---

## Navigators

### navigators: []
- **Source**: Intentionally left empty
- **How Determined**: To be populated by human with local contact information
- **Confidence**: N/A

---

## Data Gaps and Limitations

### Values Not Found in Documentation:
1. **[Field name]**: Could not locate in any source
   - Checked: [list sources checked]
   - Used default/inference: [explain]

### Values That Need Verification:
1. **[Field name]**: [Reason for uncertainty]
   - Source was unclear/incomplete
   - Recommend human review

---

## Summary

- **Total fields**: X
- **High confidence**: Y fields (directly sourced)
- **Medium confidence**: Z fields (inferred/calculated)
- **Low confidence**: N fields (defaults/assumptions)

**Key sources used**:
1. [URL 1] - Primary program page
2. [URL 2] - Application form
3. [URL 3] - Eligibility guidelines

**Recommended verification**:
- [ ] Asset limits (if marked as data gap)
- [ ] Legal status requirements (if inferred)
- [ ] Benefit value calculation (if estimated)
```

### Important Guidelines

1. **Be specific**: Don't just say "from website" - give exact URL and section
2. **Show your work**: If calculated, show the math. If paraphrased, show original quote
3. **Admit gaps**: If you couldn't find something and used a default, say so clearly
4. **Differentiate**:
   - "Extracted directly" = copied from source
   - "Paraphrased" = reworded from source
   - "Calculated" = derived from data (show formula)
   - "Inferred" = reasonable assumption (explain why)
   - "Default" = standard value used when source unclear

5. **Quote evidence**: Include short relevant quotes to prove the source supports your value

6. **Flag uncertainties**: Mark any fields where confidence is Medium or Low for human review

### Output

Return ONLY the markdown document following the structure above. This will be saved as `sources.md` in the ticket_content directory.
"""

# Dictionary for easy access
RESEARCHER_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "gather_links": GATHER_LINKS_PROMPT,
    "extract_criteria": EXTRACT_CRITERIA_PROMPT,
    "generate_test_cases": GENERATE_TEST_CASES_PROMPT,
    "generate_single_test_case": GENERATE_SINGLE_TEST_CASE_PROMPT,
    "convert_to_json": CONVERT_TO_JSON_PROMPT,
    "fix_issues": FIX_ISSUES_PROMPT,
    "generate_program_config": GENERATE_PROGRAM_CONFIG_PROMPT,
    "generate_sources_documentation": GENERATE_SOURCES_DOCUMENTATION_PROMPT,
    "test_case_categories": TEST_CASE_CATEGORIES,
}
