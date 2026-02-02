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
│  QA Validate JSON → [Fix Loop] → Create Linear Ticket → END                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **Researcher Agent**: Gathers documentation, extracts eligibility criteria, maps to screener fields, generates test cases
- **QA Agent**: Adversarial reviewer that validates research accuracy and test coverage
- **Iterative Loops**: QA issues trigger fixes until quality threshold met (max 3 iterations)
- **JSON Output**: Test cases formatted for the pre-validation system
- **Linear Integration**: Creates implementation tickets with acceptance criteria

## Installation

```bash
# Navigate into this repo (whatever you named it locally)
cd program_researcher  # or your local directory name

# Install dependencies
pip install langgraph langchain langchain-anthropic pydantic pydantic-settings \
    httpx beautifulsoup4 lxml jsonschema click rich python-dotenv
```

Or install as an editable package:

```bash
pip install -e ".[dev]"
```

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
7. **Linear Ticket**: Implementation ticket with acceptance criteria
8. **Workflow Log**: Complete execution log
9. **Summary**: Markdown summary of the research run

### Output Directory Structure

Each research run creates a timestamped directory:

```
output/
└── il_csfp_20240115_143022/     # Timestamped run directory
    ├── SUMMARY.md               # High-level summary with metrics
    ├── workflow_log.txt         # Complete execution log
    ├── gather_links.json        # Link catalog
    ├── screener_fields.json     # Available screener fields
    ├── extract_criteria.json    # Eligibility criteria and field mapping
    ├── qa_research_iter1.json   # QA validation results (per iteration)
    ├── generate_tests.json      # Human-readable test scenarios
    ├── qa_tests_iter1.json      # Test case QA results
    ├── convert_json.json        # JSON test cases
    ├── qa_json_iter1.json       # JSON QA results
    └── linear_ticket.json       # Ticket content
```

### Disabling Output Saving

To run without saving outputs (e.g., for quick testing):

```bash
python run.py research --no-save \
  --program "CSFP" \
  --state "il" \
  --white-label "il" \
  --source-url "https://www.fns.usda.gov/csfp"
```

## Workflow Steps

### Step 1: Gather Links
- Fetches provided source URLs
- Extracts all hyperlinks from content
- Identifies legislative citations (U.S. Code, CFR, state statutes)
- Categorizes and titles each link

### Step 2: Read Screener Fields
- Parses Django models from `benefits-be/screener/models.py`
- Extracts available fields, types, and valid values
- Identifies helper methods for calculations

### Step 3: Extract Criteria
- Reviews all source documentation
- Extracts eligibility criteria with citations
- Maps each criterion to screener fields
- Identifies data gaps

### Step 4: QA Validate Research
- Independent review by QA agent
- Verifies criteria accuracy against sources
- Checks for missed requirements
- Validates field mappings

### Step 5: Generate Test Cases
- Creates 10-15 human-readable scenarios
- Covers happy path, boundaries, exclusions
- Includes exact form values

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

### Step 9: Create Linear Ticket
- Formats acceptance criteria
- Includes source documentation
- Attaches JSON test file path

## Development

### Running Tests

```bash
pytest program_research_agent/tests/
```

### Code Quality

```bash
ruff check program_research_agent/
mypy program_research_agent/
```

## Project Structure

```
program_research_agent/
├── __init__.py           # Package exports
├── graph.py              # Main LangGraph definition
├── state.py              # Pydantic state models
├── config.py             # Configuration management
├── cli.py                # CLI entry point
├── nodes/                # Graph node implementations
│   ├── gather_links.py
│   ├── read_screener_fields.py
│   ├── extract_criteria.py
│   ├── qa_research.py
│   ├── generate_tests.py
│   ├── qa_tests.py
│   ├── convert_json.py
│   ├── qa_json.py
│   └── linear_ticket.py
├── tools/                # Utility tools
│   ├── web_research.py
│   ├── screener_fields.py
│   └── schema_validator.py
├── prompts/              # Agent system prompts
│   ├── researcher.py
│   └── qa_agent.py
├── tests/                # Test suite
└── output/               # Generated files
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
