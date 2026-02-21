# Model Configuration

**Last Updated**: 2026-02-19
**Strategy**: Use Sonnet for extraction, Opus for validation

## Current Configuration

```python
researcher_model = "claude-sonnet-4-5-20250929"  # Sonnet 4.5
qa_model = "claude-opus-4-6"                      # Opus 4.6
```

## Rationale

### Researcher: Sonnet 4.5
**Use for:** Extraction, generation, content creation

**Why:**
- ✅ Fast processing (important for ~20+ calls per research run)
- ✅ Cost-effective for high-volume operations
- ✅ Excellent at structured extraction tasks
- ✅ Good enough for most extraction and generation work

**Tasks:**
- Link discovery and enhancement
- Criteria extraction and field mapping
- Test case generation (14 scenarios)
- JSON conversion
- Program config generation
- Ticket creation

### QA Agent: Opus 4.6
**Use for:** Validation, error detection, quality control

**Why:**
- ✅ **Most accurate** - Critical for catching subtle errors
- ✅ **Better reasoning** - Validates complex logic and mappings
- ✅ **Last line of defense** - Prevents bad data from reaching production
- ✅ **Cost-effective placement** - Only ~9 calls per research run (3 iterations × 3 phases)
- ✅ **High stakes** - QA mistakes are expensive (wrong configs, failed tests, wasted dev time)

**Tasks:**
- Research QA (validates extraction accuracy)
- Test Case QA (validates test coverage and correctness)
- JSON QA (validates schema compliance)

## Cost Analysis

**Per research run:**
- **Researcher (Sonnet)**: ~20-25 calls × $3/MTok = ~$0.60-0.75
- **QA (Opus)**: ~9 calls × $15/MTok = ~$1.35
- **Fix nodes (Sonnet)**: ~5-10 calls × $3/MTok = ~$0.15-0.30
- **Total**: ~$2.10-2.40 per program

**If using Sonnet for QA instead:**
- **QA (Sonnet)**: ~9 calls × $3/MTok = ~$0.27
- **Savings**: ~$1.08 per program
- **Trade-off**: Lower accuracy, more errors slip through

**If using Opus for everything:**
- **Total**: ~$6-7.50 per program
- **Extra cost**: ~$4-5 per program
- **Trade-off**: Minimal quality improvement for extraction tasks

## Performance Impact

| Model | Latency (per call) | Quality | Use Case |
|-------|-------------------|---------|----------|
| Haiku 4.5 | ~2s | Good | Not recommended |
| Sonnet 4.5 | ~5s | Excellent | ✅ Extraction & generation |
| Opus 4.6 | ~10s | Best | ✅ Validation & QA |

**Research run time:**
- Current config: ~5 min (balanced)
- All Sonnet: ~3 min (faster, less accurate)
- All Opus: ~10 min (slower, minimal improvement)

## Quality Impact

### Real Example: Middle-Income Rental Program

**With Sonnet QA (old config):**
- ❌ Income limits extracted as "≤80%" instead of "80-120%" (CRITICAL ERROR)
- ❌ Senior asset limit ($150K) missed
- ❌ 3 QA iterations couldn't fix the income error

**Expected with Opus QA:**
- ✅ Opus more likely to catch the income range error
- ✅ Better at noticing "middle-income" vs "low-income" discrepancy
- ✅ Stronger reasoning about eligibility logic

## Override Options

You can override these via environment variables:

```bash
# Use Opus for everything (thorough but expensive)
export RESEARCH_AGENT_RESEARCHER_MODEL="claude-opus-4-6"
export RESEARCH_AGENT_QA_MODEL="claude-opus-4-6"

# Use Sonnet for everything (fast but less accurate QA)
export RESEARCH_AGENT_RESEARCHER_MODEL="claude-sonnet-4-5-20250929"
export RESEARCH_AGENT_QA_MODEL="claude-sonnet-4-5-20250929"

# Use Haiku for testing (fast and cheap, not recommended for production)
export RESEARCH_AGENT_RESEARCHER_MODEL="claude-haiku-4-5-20251001"
```

## Recommendations

### Current (Default) ✅
**Sonnet for extraction, Opus for QA**
- Best balance of speed, cost, and quality
- Recommended for production use

### Alternative 1: All Opus
**When to use:** Critical programs where accuracy is paramount and cost/speed don't matter
- Example: Federal programs with complex regulations
- Set: `RESEARCH_AGENT_RESEARCHER_MODEL=claude-opus-4-6`

### Alternative 2: All Sonnet
**When to use:** Testing, development, or when budget is very tight
- Not recommended for production
- Set: `RESEARCH_AGENT_QA_MODEL=claude-sonnet-4-5-20250929`

## Monitoring

Track QA effectiveness:
1. Count critical errors caught by QA
2. Measure false positives (QA flags non-issues)
3. Track errors that slip through to production

If Opus QA isn't catching more errors than Sonnet would, consider reverting to save cost.

## Future Considerations

- **Claude 5 models**: Update when available
- **Specialized models**: If Anthropic releases QA-specific models
- **Cost optimization**: Batch processing, caching, or streaming
- **A/B testing**: Compare Opus vs Sonnet QA on sample programs
