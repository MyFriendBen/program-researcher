"""
Helper functions for processing vision content in LangChain messages.
"""

import json
from typing import Any


def is_pdf_vision_content(content: str) -> bool:
    """Check if content is a PDF vision data structure."""
    try:
        data = json.loads(content)
        return isinstance(data, dict) and data.get("type") == "pdf_vision"
    except (json.JSONDecodeError, TypeError):
        return False


def create_vision_message_content(pdf_vision_data: dict, prompt: str) -> list[dict[str, Any]]:
    """
    Create LangChain message content with images for vision processing.

    Args:
        pdf_vision_data: Dict with images_base64 and metadata
        prompt: Text prompt to accompany the images

    Returns:
        List of content blocks for LangChain message (text + images)
    """
    content_blocks = []

    # Add text prompt first
    content_blocks.append({"type": "text", "text": prompt})

    # Add each page image
    for i, image_base64 in enumerate(pdf_vision_data["images_base64"], 1):
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                },
            }
        )

        # Add page marker between images
        if i < len(pdf_vision_data["images_base64"]):
            content_blocks.append({"type": "text", "text": f"\n--- Page {i + 1} ---\n"})

    return content_blocks


def create_vision_prompt_for_pdf(
    pdf_url: str,
    focus: str = "Extract all eligibility criteria, asset limits, and preference criteria",
) -> str:
    """
    Create a focused prompt for PDF vision extraction.

    Args:
        pdf_url: URL of the PDF being analyzed
        focus: What to focus on extracting

    Returns:
        Formatted prompt for vision extraction
    """
    return f"""You are analyzing a PDF document from: {pdf_url}

**Task**: {focus}

**Instructions for reading this PDF:**

1. **Look for section headings** - They are usually:
   - ALL CAPS (e.g., "ASSET", "PREFERENCE POINTS")
   - Larger or bold text
   - Visually separated from content below

2. **Extract structured data**:
   - Dollar amounts under "ASSET" or "RESOURCE" sections
   - Point values under "PREFERENCE" or "PRIORITY" sections
   - Percentage thresholds under "INCOME" or "ELIGIBILITY" sections
   - Age requirements, household size limits, etc.

3. **Capture exact values**:
   - If you see "$75,000", report exactly "$75,000"
   - If you see "12 points", report exactly "12 points"
   - If you see exceptions (e.g., "higher limit for 62+"), include those

4. **Note the structure**:
   - Report which section each value came from
   - Include any conditions or exceptions
   - Preserve bullet point lists

**Format your response as:**
```
Section: [HEADING NAME]
- Criterion 1: [details and values]
- Criterion 2: [details and values]

Section: [NEXT HEADING]
- Criterion 1: [details and values]
```

Include the actual dollar amounts, point values, and thresholds you see in the document.
"""
