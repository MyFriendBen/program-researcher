# Program Research Agent

A LangGraph-based multi-agent system for researching benefit programs, validating eligibility criteria, generating test cases, and creating implementation tickets.

## Overview

This tool automates the research phase of adding new benefit programs to the MyFriendBen platform. It follows the process outlined in `plans/qa/AI_PROGRAM_QA_PROCESS.md` but runs **before** implementation begins, ensuring research drives development.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LangGraph State Machine                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Gather Links → Read Fields → Extract Criteria → QA Validate Research       │
│                                                        ↓                    │
│                                              [Fix Loop if needed]           │
│                                                        ↓                    │
│  Generate Tests → QA Validate Tests → [Fix Loop] → Convert JSON             │
│                                                        ↓                    │
│  QA Validate JSON → [Fix Loop] → Generate Program Config                    │
│                                                        ↓                    │
│                                              Create Ticket → END            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **Researcher Agent**: Gathers documentation, extracts eligibility criteria, maps to screener fields, generates test cases
- **PDF Vision Processing**: Automatically converts PDFs to images and uses Claude's vision to extract structured data (headings, bullets, dollar amounts) with 10x better accuracy than text extraction
- **QA Agent**: Adversarial reviewer that validates research accuracy and test coverage
- **Iterative Loops**: QA issues trigger fixes until quality threshold met (max 3 iterations)
- **Program Config Generation**: Auto-generates Django admin import configuration
- **JSON Output**: Test cases formatted for the pre-validation system
- **Linear Integration**: Creates implementation tickets with acceptance criteria (optional)

## Installation

```bash
# Navigate into this repo (whatever you named it locally)
cd program-researcher

# Install Python dependencies
pip install -r requirements.txt

# Install system dependency for PDF processing (macOS)
brew install poppler

# For Linux:
# sudo apt-get install poppler-utils
```

Or install as an editable package:

```bash
pip install -e ".[dev]"
brew install poppler  # Still need system dependency
```

### Dependencies

Core dependencies:
- `langgraph`, `langchain`, `langchain-anthropic` - AI framework
- `pydantic` - Data validation
- `httpx`, `beautifulsoup4` - Web scraping
- `pdf2image`, `PyPDF2` - **NEW**: PDF vision processing
- `click`, `rich` - CLI interface

**Note**: `pdf2image` requires the `poppler` system library for PDF rendering. Install it with your system package manager before running the tool.

## Configuration

Set your Anthropic API key as an environment variable:

```bash
export RESEARCH_AGENT_ANTHROPIC_API_KEY=sk-ant-...
```

Optional: For Linear ticket creation, also set:

```bash
export RESEARCH_AGENT_LINEAR_API_KEY=lin_api_...
export RESEARCH_AGENT_LINEAR_TEAM_ID=your-team-id
export RESEARCH_AGENT_LINEAR_PROJECT_ID=your-project-id
```

You can also create a `.env` file in the repo root with these values.

## Usage

### CLI (Recommended)

**Important**: Run all commands from within this repo directory using `run.py`. This ensures imports work regardless of what you named your local clone.

```bash
# Navigate into the repo first
cd /path/to/your-repo-name  # whatever you named it locally

# Research a program
python run.py research \
  --program "CSFP" \
  --state "il" \
  --white-label "il" \
  --source-url "https://www.fns.usda.gov/csfp" \
  --source-url "https://www.dhs.state.il.us/page.aspx?item=30513"

# Preview workflow without executing (no API key required)
python run.py research --dry-run \
  --program "CSFP" \
  --state "il" \
  --white-label "il" \
  --source-url "https://www.fns.usda.gov/csfp"

# Show graph structure
python run.py graph

# Get help
python run.py --help
python run.py research --help
```

### Python API

Run the example script from within the repo:

```bash
cd /path/to/your-repo-name
python examples/research_csfp.py
```

Or create your own script (must be run from within the repo directory):

```python
import asyncio
from program_research_agent.graph import run_research

async def main():
    state = await run_research(
        program_name="CSFP",
        state_code="il",
        white_label="il",
        source_urls=[
            "https://www.fns.usda.gov/csfp",
            "https://www.dhs.state.il.us/page.aspx?item=30513",
        ],
        max_iterations=3,
    )

    print(f"Status: {state.status}")
    print(f"Test cases generated: {len(state.json_test_cases)}")
    print(f"Linear ticket: {state.linear_ticket_url}")

asyncio.run(main())
```

## Output

The tool produces outputs at each step and saves them to timestamped directories for debugging and auditing.

### What Gets Saved

1. **Link Catalog**: All documentation URLs discovered and categorized
2. **Screener Fields**: Available fields from Django models
3. **Field Mapping**: Eligibility criteria mapped to screener fields, with data gaps identified
4. **QA Results**: Validation results at each QA step (with iteration numbers)
5. **Human Test Cases**: 10-15 scenarios for manual QA testing
6. **JSON Test Cases**: Test data in `pre_validation_schema.json` format
7. **Program Config**: Django admin import configuration (ready to use)
8. **Linear Ticket**: Implementation ticket with acceptance criteria (if Linear configured)
9. **Workflow Log**: Complete execution log
10. **Summary**: Markdown summary of the research run

### Output Directory Structure

Each research run creates a timestamped directory:

```
output/
└── il_csfp_20240115_143022/            # Timestamped run directory
    ├── ticket_content/                  # Files for ticket/review
    │   ├── il_csfp_initial_config.json # Django admin config
    │   ├── il_csfp_test_cases.json     # JSON test cases
    │   └── il_csfp_ticket.md            # Ticket markdown
    ├── SUMMARY.md                       # High-level summary with metrics
    ├── workflow_log.txt                 # Complete execution log
    ├── gather_links.json                # Link catalog
    ├── screener_fields.json             # Available screener fields
    ├── extract_criteria.json            # Eligibility criteria and field mapping
    ├── qa_research_iter1.json           # QA validation results (per iteration)
    ├── generate_tests.json              # Human-readable test scenarios
    ├── qa_tests_iter1.json              # Test case QA results
    ├── convert_json.json                # JSON test cases
    ├── qa_json_iter1.json               # JSON QA results
    └── generate_program_config.json     # Program config generation output
```

### Error Handling

If the workflow fails, `SUMMARY.md` will include:
- **Error details**: The specific error message and context
- **Next steps**: Actionable guidance on how to fix the issue
- **Last 15 workflow messages**: Full context of what happened

The summary is always saved, even when the workflow fails, so you can diagnose issues.

### Disabling Output Saving

To run without saving outputs (e.g., for quick testing):

```bash
python run.py research --no-save \
  --program "CSFP" \
  --state "il" \
  --white-label "il" \
  --source-url "https://www.fns.usda.gov/csfp"
```

## PDF Vision Processing

The researcher uses **Claude's vision capabilities** to read PDFs, which dramatically improves accuracy for extracting structured data.

### Why Vision for PDFs?

**Traditional text extraction** loses structure:
```
"ASSET Household assets may not exceed $75,000 Households..."
```
Everything becomes a text blob with no formatting cues.

**Vision-based extraction** preserves layout:
- Sees section headings (ALL CAPS, bold, large text)
- Understands bullet points and indentation
- Identifies emphasized values (bold dollar amounts)
- Reads tables and structured lists naturally

### What Gets Extracted Better

- ✅ **Asset limits**: "$75,000" (not "$100,000" or missed entirely)
- ✅ **Preference criteria**: "12 points for residency, 5 points for employment"
- ✅ **Age exceptions**: "$150,000 for households where all members are 62+"
- ✅ **Screening requirements**: "credit check, CORI background check, references"

### Cost Impact

- Text extraction: ~$0.015 per 5-page PDF
- Vision extraction: ~$0.035 per 5-page PDF (+$0.02)
- **Result**: +133% cost but ~10x better accuracy

For typical research (1-2 PDFs): adds ~$0.04 per program run.

## Workflow Steps

### Step 1: Gather Links
- Fetches provided source URLs
- **For PDFs**: Converts to PNG images for vision processing
- Extracts all hyperlinks from HTML content
- Identifies legislative citations (U.S. Code, CFR, state statutes)
- Categorizes and titles each link

### Step 2: Read Screener Fields
- Parses Django models from `benefits-be/screener/models.py`
- Extracts available fields, types, and valid values
- Identifies helper methods for calculations

### Step 3: Extract Criteria
- Reviews all source documentation
- **For PDFs**: Uses Claude's vision to read structure (headings, bullets, emphasis)
- Extracts eligibility criteria with citations (including dollar amounts, point values)
- Maps each criterion to screener fields
- Identifies data gaps

### Step 4: QA Validate Research
- Independent review by QA agent
- Verifies criteria accuracy against sources
- Checks for missed requirements
- Validates field mappings

### Step 5: Generate Test Cases
- Generates test cases **one at a time** to prevent response truncation
- Creates 14 scenarios across categories (happy path, income thresholds, age thresholds, exclusions, multi-member)
- Includes exact form values and expected outcomes
- Resilient to individual failures - continues generating remaining test cases

### Step 6: QA Validate Tests
- Reviews test coverage
- Validates boundary conditions
- Checks expected outcomes

### Step 7: Convert to JSON
- Transforms to `pre_validation_schema.json` format
- Validates against schema
- Calculates ages from birth dates

### Step 8: QA Validate JSON
- Compares JSON to human-readable source
- Verifies schema compliance
- Checks for data mismatches

### Step 9: Generate Program Config
- Creates Django admin import configuration
- Extracts official program name and description from research
- Identifies application links and required documents
- Generates config ready for human review

### Step 10: Create Linear Ticket (Optional)
- Formats acceptance criteria
- Includes source documentation
- Embeds program configuration
- Attaches test case files

## Development

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
ruff check .
mypy .
```

## Project Structure

```
program-researcher/
├── run.py                    # Entry point script (handles module aliasing)
├── __init__.py               # Package exports
├── graph.py                  # Main LangGraph definition
├── state.py                  # Pydantic state models
├── config.py                 # Configuration management
├── cli.py                    # CLI commands
├── nodes/                    # Graph node implementations
│   ├── gather_links.py
│   ├── read_screener_fields.py
│   ├── extract_criteria.py
│   ├── qa_research.py
│   ├── generate_tests.py
│   ├── qa_tests.py
│   ├── convert_json.py
│   ├── qa_json.py
│   └── linear_ticket.py
├── tools/                    # Utility tools
│   ├── web_research.py       # Web fetching and PDF handling
│   ├── pdf_vision.py         # NEW: PDF to image conversion
│   ├── vision_helper.py      # NEW: Vision message formatting
│   ├── screener_fields.py
│   ├── schema_validator.py
│   └── output_saver.py       # Step output and summary generation
├── prompts/                  # Agent system prompts
│   ├── researcher.py
│   └── qa_agent.py
├── tests/                    # Test suite
├── examples/                 # Example scripts
│   └── research_csfp.py
└── output/                   # Generated files (gitignored)
```

## Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `RESEARCH_AGENT_ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `RESEARCH_AGENT_LINEAR_API_KEY` | Linear API key | Optional |
| `RESEARCH_AGENT_LINEAR_TEAM_ID` | Linear team ID | Optional |
| `RESEARCH_AGENT_LINEAR_PROJECT_ID` | Linear project ID | Optional |
| `RESEARCH_AGENT_RESEARCHER_MODEL` | Model for researcher agent | claude-sonnet-4-20250514 |
| `RESEARCH_AGENT_QA_MODEL` | Model for QA agent | claude-sonnet-4-20250514 |
| `RESEARCH_AGENT_MAX_QA_ITERATIONS` | Default max QA iterations | 3 |

## License

Internal tool for MyFriendBen platform.
