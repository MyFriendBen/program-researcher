# PDF Reading: Vision vs Text Extraction

**Context**: AI researcher is missing structured data (asset limits, preference criteria) from PDFs

---

## The Problem

Current text extraction approach loses visual structure:
```
Text blob: "Gift Income ASSET PREFERENCE POINTS Cambridge residency Asset limits apply
Household assets may not exceed $75,000 Households in which all members are 62..."
```

Key information becomes buried in continuous text with no visual cues about:
- What's a heading vs content
- What's a bullet point vs paragraph
- What values belong under which section

---

## Comparison

### Current: Text Extraction (PyPDF2, pdfplumber)

**How it works**:
```python
import PyPDF2
pdf = PyPDF2.PdfReader('application.pdf')
text = pdf.pages[0].extract_text()
# Result: "ASSET Household assets may not exceed $75,000..."
```

**Pros**:
- ✅ Fast
- ✅ Precise text extraction
- ✅ Easy to search/regex
- ✅ Lower token cost

**Cons**:
- ❌ Loses formatting (bold, font size, colors)
- ❌ Loses spatial layout (sections, columns, indentation)
- ❌ No visual hierarchy (headings vs content)
- ❌ Struggles with tables and structured lists
- ❌ Everything becomes one text stream

**Result for our case**:
- Sees "asset verification" mentioned
- Cannot identify "ASSET" as section heading
- Cannot distinguish "$75,000" as the key value
- Cannot parse bullet point list of criteria

---

### Alternative: Vision-Based Reading (Claude Vision API)

**How it works**:
```python
from pdf2image import convert_from_path
import anthropic

# Convert PDF to images
images = convert_from_path('application.pdf')

# Send to Claude vision
client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode()
                }
            },
            {
                "type": "text",
                "text": "Extract asset limits and preference criteria from this form"
            }
        ]
    }]
)
```

**Pros**:
- ✅ **Sees visual hierarchy**: Bold headings, font sizes
- ✅ **Understands layout**: Sections, columns, indentation
- ✅ **Reads tables naturally**: Can parse tabular data visually
- ✅ **Contextual understanding**: "$75,000" is clearly under "ASSET" heading
- ✅ **Formatting cues**: Bullet points, emphasis, spacing
- ✅ **Handles complex layouts**: Multi-column, sidebars, boxes

**Cons**:
- ❌ Slower (image processing + larger context)
- ❌ Higher token cost (images use more tokens)
- ❌ Requires image conversion (PDF → PNG)
- ❌ May have OCR errors on poor quality scans

**Result for our case**:
- Would SEE "ASSET" as a large/bold heading
- Would SEE bullet points with distinct criteria
- Would clearly identify "$75,000" as the primary limit
- Would see "$150,000" as the exception for 62+
- Would SEE "PREFERENCE POINTS" section with point values

---

## Visual Example

### What Text Extraction Sees:
```
ASSET Household assets may not exceed $75,000. Households in which all members
are 62 or over, or where all members are disabled, may be eligible for a higher
asset limit up to $150,000. PREFERENCE POINTS The City assigns points...
```

### What Vision Sees:
```
┌────────────────────────────────────────────┐
│                                            │
│  ASSET                   ← Large, bold     │
│                                            │
│  • Household assets may not exceed         │
│    $75,000.              ← Clearly visible │
│                                            │
│  • Households in which all members are     │
│    62 or over, or where all members are    │
│    disabled, may be eligible for a         │
│    higher asset limit up to $150,000.      │
│                             ← Clear number │
│                                            │
│  PREFERENCE POINTS       ← Another heading │
│                                            │
│  The City assigns points to households...  │
│                                            │
└────────────────────────────────────────────┘
```

Vision can understand:
- "ASSET" is a heading (not just another word)
- Two bullet points are separate criteria
- "$75,000" and "$150,000" are the key values
- These values belong to the "ASSET" section

---

## Recommendation: Hybrid Approach

Use **text extraction first**, then **vision for gaps**:

```python
def extract_pdf_intelligently(pdf_url):
    # Step 1: Try text extraction (fast)
    text = extract_text_from_pdf(pdf_url)

    # Step 2: Search for key terms
    has_asset_section = 'ASSET' in text
    has_dollar_amounts = re.search(r'\$[\d,]+', text)

    # Step 3: If found terms but can't extract values, use vision
    if has_asset_section and not extracted_asset_limit:
        print("⚠️  Found 'ASSET' section but couldn't extract limit")
        print("🔍 Switching to vision mode for this section...")

        # Convert specific pages to images
        images = pdf_to_images(pdf_url)

        # Use vision to extract from each page
        for i, img in enumerate(images):
            response = claude_vision(
                image=img,
                prompt="Look for a section titled 'ASSET' or 'ASSETS'. Extract any dollar limits mentioned."
            )

    return combined_results
```

### Benefits:
- Fast text extraction for most content
- Vision only when needed (saves tokens/cost)
- Best of both: speed + accuracy
- Fallback mechanism ensures nothing is missed

---

## Implementation for Program Researcher

### Option 1: Add Vision as Secondary Pass (Recommended)

1. **Gather Links** - includes PDF URL
2. **Extract Criteria (Text)** - tries text extraction first
3. **Identify Gaps** - detects missing critical fields (asset limits, preferences)
4. **Vision Extraction** - converts relevant PDF pages to images, uses Claude vision
5. **Merge Results** - combines text + vision findings

### Option 2: Vision-First for Application PDFs

For known application forms, use vision directly:
```python
if pdf_url.endswith('application.pdf') or 'app.pdf' in pdf_url:
    # Application forms are highly structured - use vision
    return extract_via_vision(pdf_url)
else:
    # Informational PDFs - text extraction fine
    return extract_via_text(pdf_url)
```

### Option 3: Parallel Extraction

Run both simultaneously, merge results:
```python
text_results = extract_text(pdf) # Fast
vision_results = extract_vision(pdf) # Slower

# Merge: prefer vision for structured data, text for quotes
final_results = merge_extraction(text_results, vision_results)
```

---

## Prompt Changes for Vision Mode

Current prompt:
```
2. **Extract ALL eligibility criteria**, including:
   - Asset/resource limits
```

Enhanced for vision:
```
2. **Extract ALL eligibility criteria**:

   For PDFs:
   - Look for section headings (usually ALL CAPS or bold)
   - When you see "ASSET" or "RESOURCE" heading, examine the content below it
   - Look for bullet points or numbered lists under headings
   - Extract dollar amounts that appear near asset/resource terms

   For Images/Vision mode:
   - Identify large or bold text as section headings
   - Read indented or bulleted content under each heading
   - Note emphasized values (bold, larger font, highlighted)
   - Extract values from tables or structured layouts
```

---

## Cost Comparison

### Text Extraction:
- PDF parsing: Negligible
- Tokens: ~1,000 tokens per page (text only)
- Cost: ~$0.003 per page (Sonnet 3.5)

### Vision Mode:
- Image conversion: Negligible (using pdf2image)
- Tokens: ~1,500-2,000 tokens per image (base64 overhead)
- Cost: ~$0.005-0.007 per page (Sonnet 3.5 with vision)

**For 5-page application form**:
- Text only: $0.015
- Vision only: $0.035
- Hybrid (text + 2 pages vision): $0.020

**Verdict**: Hybrid approach adds ~33% cost but could 10x the accuracy for structured data.

---

## Next Steps

1. **Test vision extraction**: Convert middle-income PDF to images, prompt Claude vision for asset limits
2. **Compare results**: Vision vs text extraction on same document
3. **Implement hybrid**: Add vision fallback when text extraction misses critical fields
4. **Update prompts**: Add vision-specific instructions for structured data
5. **Measure improvement**: Re-run research, check if $75,000 is captured

---

## Related Tools

- **pdf2image**: Convert PDF pages to PIL images
- **base64**: Encode images for Claude API
- **anthropic SDK**: Supports vision in messages API
- **PyPDF2**: Current text extraction (keep for fallback)

---

## Conclusion

**Yes, there IS a difference!** Vision-based PDF reading would likely solve the asset limit extraction problem because it can:
- See section headings visually
- Understand bullet point structure
- Identify emphasized dollar amounts
- Parse structured forms naturally

For the program researcher, implementing a **hybrid approach** (text first, vision for gaps) would provide the best balance of speed, cost, and accuracy.
