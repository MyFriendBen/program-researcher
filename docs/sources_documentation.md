# Sources Documentation Feature

**Added**: 2026-02-18

## Overview

The program researcher now includes prompts to generate a `sources.md` file that documents where each value in the program configuration came from. This provides transparency and makes it easy to verify AI research quality.

## What It Does

For EACH field in the program config JSON, the sources documentation shows:
- The field name and value
- The specific source (URL, PDF page, section)
- How the value was determined (extracted, calculated, inferred, default)
- Confidence level (High, Medium, Low)
- Relevant quotes or evidence from sources
- Flags for values that need human verification

## Example Output

See: `/Users/jm/code/mfb/program-researcher/output/ma_Middle-Income Rental Program_20260218_094045/ticket_content/sources.md`

Key sections:
```markdown
### program.estimated_application_time: "1 - 2 hours"
- **Source**: Estimated from application form complexity
- **How Determined**: Analyzed PDF form
  - Form is 5 pages long
  - Approximately 40-50 fields
  - Complex income/asset calculations
- **Confidence**: Medium
- **Notes**: ⚠️ CSV research shows "2 hours" - could refine to exact "2 hours"

### program.legal_status_required: ["citizen"]
- **Source**: Not explicitly stated in documentation
- **How Determined**: Inferred from standard federal housing program requirements
- **Confidence**: Low ⚠️
- **Notes**: ⚠️ Human verification needed - CSV indicates "NA"
```

## Benefits

1. **Transparency**: Shows exactly where each value came from
2. **Verification**: Makes it easy to spot incorrect inferences or missing data
3. **Confidence Tracking**: Flags low-confidence fields for human review
4. **Gap Identification**: Clearly documents what couldn't be found
5. **Quality Control**: Helps identify when AI is guessing vs extracting facts

## Prompt Location

- **File**: `/Users/jm/code/mfb/program-researcher/prompts/researcher.py`
- **Prompt**: `GENERATE_SOURCES_DOCUMENTATION_PROMPT`
- **Dictionary key**: `"generate_sources_documentation"`

## Integration Status

⚠️ **NOT YET INTEGRATED INTO WORKFLOW**

The prompt has been created but needs to be integrated into the graph workflow:

1. Add node to `graph.py` that calls this prompt after program config generation
2. Pass program_config JSON and research_context to the prompt
3. Save output as `sources.md` in ticket_content directory

### Implementation Steps

```python
# In graph.py, after generate_program_config node:

def generate_sources_documentation(state: ResearchState) -> dict:
    """Generate sources.md documenting where each config value came from."""

    program_config = state.get("program_config")
    research_context = {
        "links": state.get("links"),
        "criteria": state.get("eligibility_criteria"),
        "test_cases": state.get("test_cases_human"),
    }

    prompt = RESEARCHER_PROMPTS["generate_sources_documentation"].format(
        program_name=state["program_name"],
        state_code=state["state_code"],
        white_label=state["white_label"],
        program_config=json.dumps(program_config, indent=2),
        research_context=json.dumps(research_context, indent=2),
        date=datetime.now().strftime("%Y-%m-%d")
    )

    response = llm.invoke(prompt)
    sources_md = response.content

    # Save to ticket_content
    output_dir = Path(state["output_dir"]) / "ticket_content"
    sources_path = output_dir / f"{state['white_label']}_{state['program_name']}_sources.md"
    sources_path.write_text(sources_md)

    return {"sources_documentation": sources_md}

# Add to graph after program config generation
graph.add_node("generate_sources_doc", generate_sources_documentation)
graph.add_edge("generate_program_config", "generate_sources_doc")
```

## Quality Indicators

The sources.md file helps identify quality issues:

### High Confidence Indicators ✅
- Direct quotes from official sources
- Specific URL + section references
- Extracted from application PDFs
- System-generated values (white_label, year)

### Medium Confidence Indicators ⚠️
- Paraphrased from sources
- Calculated from available data
- Estimated based on form complexity
- Synthesized from multiple sources

### Low Confidence Indicators ❌
- Inferred from "standard practice"
- Default values used
- No source found
- Contradicts other research (like CSV)

## Recommended Review Process

1. **Before implementation**, human reviewer should:
   - Check all Low confidence fields
   - Verify fields flagged with ⚠️
   - Compare to any existing research (like CSV)

2. **Focus on critical gaps**:
   - Asset limits
   - Citizenship requirements (especially if inferred)
   - Benefit value calculations
   - Application time estimates

3. **Use sources.md as checklist**:
   - Each flagged item should be verified against original source
   - Update config JSON based on findings
   - Document corrections in sources.md

## Future Enhancements

1. **Automated confidence scoring**: Calculate overall research quality score
2. **Comparison mode**: Auto-compare to human CSV research if available
3. **Source verification**: Auto-check that URLs are still accessible
4. **Gap prioritization**: Rank missing data by importance to eligibility calculation
