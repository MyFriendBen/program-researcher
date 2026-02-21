# Linear Ticket Workflow

Guide for using Linear tickets with the program-researcher tool.

## Quick Start

### 1. Run Research (Creates Ticket)

```bash
cd program-researcher

python run.py research \
  --program "CSFP" \
  --state "il" \
  --white-label "il" \
  --source-url "https://www.fns.usda.gov/csfp"
```

### 2. Review Ticket or Local Output

**With Linear configured:**
- Ticket created at: `https://linear.app/mfb/issue/LIN-1234`
- Review eligibility criteria, test cases, and program config

**Without Linear configured:**
- Files saved to: `output/il_CSFP_20260214_163629/ticket_content/`
- Review locally before implementation

### 3. Implement from Ticket

```bash
# In Claude Code
/add-program LIN-1234
```

Or use local files if Linear isn't configured.

## Output Structure

Each research run creates a timestamped directory:

```
output/il_CSFP_20260214_163629/
├── ticket_content/                          ← Files for ticket/review
│   ├── il_CSFP_initial_config.json         ← Django admin config
│   ├── il_CSFP_test_cases.json             ← Test scenarios
│   └── il_CSFP_ticket.md                    ← Ticket markdown
├── SUMMARY.md                                ← Research overview
├── extract_criteria.json                    ← Detailed field mappings
├── generate_program_config.json             ← Config generation output
└── workflow_log.txt                         ← Full execution log
```

## What's in the Config File

The `il_CSFP_initial_config.json` contains Django admin import data:

```json
{
  "white_label": {"code": "il"},
  "program_category": {"external_name": "il_food"},
  "program": {
    "name": "Commodity Supplemental Food Program (CSFP)",
    "description": "Two paragraph description...",
    "apply_button_link": "https://apply.here/",
    "legal_status_required": ["citizen", "refugee"],
    ...
  },
  "documents": [...],
  "navigators": []
}
```

**Human Review Needed:**
- Verify program description is accurate
- Confirm application link works
- Add navigator contacts if available

## Linear Integration (Optional)

### Enable Linear Ticket Creation

```bash
# .env file in program-researcher/
RESEARCH_AGENT_LINEAR_API_KEY=lin_api_xxxxx
RESEARCH_AGENT_LINEAR_TEAM_ID=your-team-id
RESEARCH_AGENT_LINEAR_PROJECT_ID=your-project-id  # Optional
```

### Benefits of Linear Integration

✅ Single source of truth for all team members
✅ Track implementation status on Linear board
✅ Link PRs to tickets automatically
✅ Work from any machine without local files

### Without Linear

If Linear isn't configured, all files are saved locally:
- Review `ticket_content/` directory
- Share files with team as needed
- Still get all research outputs

## Workflow Integration

```
Research → Review → Implement

1. program-researcher generates config + test cases
2. Human reviews ticket or local files
3. /add-program implements from ticket or local files
4. CodeRabbit + human review PR
```

## Error Handling

**Ticket not found:**
- Verify ticket ID format (LIN-1234)
- Check Linear access permissions

**Missing research data:**
- Ticket may not be from program-researcher
- Verify ticket has structured research sections

**Local files missing:**
- OK if using Linear tickets
- Run research again or get files from teammate
