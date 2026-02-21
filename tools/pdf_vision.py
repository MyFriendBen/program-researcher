"""
PDF Vision Extraction Tool

Converts PDFs to images and uses Claude's vision capabilities to extract structured data.
This preserves visual layout, formatting, and hierarchy that text extraction loses.
"""

import base64
import tempfile
from pathlib import Path
from typing import Any

import httpx
from pdf2image import convert_from_bytes, convert_from_path


async def download_pdf(url: str) -> bytes:
    """Download a PDF from a URL."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def pdf_to_images(pdf_source: str | bytes, dpi: int = 150, max_pages: int = 20) -> list[bytes]:
    """
    Convert PDF to PNG images.

    Args:
        pdf_source: Either a file path (str) or PDF bytes
        dpi: Resolution for conversion (150 is good balance of quality/size)
        max_pages: Maximum number of pages to convert

    Returns:
        List of PNG image bytes
    """
    # Convert PDF to PIL images
    if isinstance(pdf_source, str):
        images = convert_from_path(pdf_source, dpi=dpi, last_page=max_pages)
    else:
        images = convert_from_bytes(pdf_source, dpi=dpi, last_page=max_pages)

    # Convert PIL images to PNG bytes
    png_bytes_list = []
    for img in images:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, "PNG")
            with open(tmp.name, "rb") as f:
                png_bytes_list.append(f.read())
            Path(tmp.name).unlink()  # Clean up temp file

    return png_bytes_list


def encode_image_base64(image_bytes: bytes) -> str:
    """Encode image bytes to base64 string for Claude API."""
    return base64.b64encode(image_bytes).decode("utf-8")


async def extract_pdf_with_vision(
    pdf_url: str,
    prompt: str = "Extract all text, structure, and data from this document. Pay special attention to headings, bullet points, dollar amounts, and structured lists.",
    max_pages: int = 10,
) -> dict[str, Any]:
    """
    Extract content from a PDF using Claude's vision capabilities.

    This approach:
    1. Downloads the PDF
    2. Converts each page to PNG image
    3. Sends images to Claude with vision prompt
    4. Returns structured extraction results

    Args:
        pdf_url: URL of the PDF to extract
        prompt: Instruction for what to extract from the PDF
        max_pages: Maximum pages to process (to control cost)

    Returns:
        Dict with:
            - url: The PDF URL
            - page_count: Number of pages processed
            - pages: List of per-page extractions
            - combined_content: All pages combined
    """
    # Download PDF
    pdf_bytes = await download_pdf(pdf_url)

    # Convert to images
    page_images = pdf_to_images(pdf_bytes, dpi=150, max_pages=max_pages)

    # For now, return the structure that will be filled by the agent
    # The actual Claude API call happens in the agent/node using the images
    return {
        "url": pdf_url,
        "page_count": len(page_images),
        "images_base64": [encode_image_base64(img) for img in page_images],
        "ready_for_vision": True,
    }


def format_pdf_vision_prompt(
    base_prompt: str,
    focus_areas: list[str] | None = None,
) -> str:
    """
    Format a prompt for PDF vision extraction with specific focus areas.

    Args:
        base_prompt: Base instruction for extraction
        focus_areas: Specific things to look for (e.g., ["asset limits", "preference criteria"])

    Returns:
        Enhanced prompt for vision extraction
    """
    prompt = base_prompt

    if focus_areas:
        prompt += "\n\n**Focus on these specific items:**\n"
        for item in focus_areas:
            prompt += f"- {item}\n"

    prompt += """
**Important instructions for reading this document:**

1. **Identify section headings** - Look for text that is:
   - Larger font size
   - Bold or emphasized
   - ALL CAPS
   - Visually separated from content below

2. **Read structured lists** - Pay attention to:
   - Bullet points (●, •, -, *)
   - Numbered lists
   - Indentation showing hierarchy
   - Items grouped under headings

3. **Extract numeric values** - Look for:
   - Dollar amounts ($XX,XXX)
   - Percentages (XX%)
   - Ranges (XX-YY)
   - Thresholds and limits

4. **Capture visual emphasis** - Note when text is:
   - Bold or highlighted
   - In a box or table
   - Larger or different color
   - Visually separated

5. **Preserve structure** - When reporting, indicate:
   - Which heading a value appears under
   - What section contains each criterion
   - How items are grouped or related

**Output format:**
For each section found, provide:
- Section heading (if any)
- Content/criteria under that heading
- Any specific values (dollar amounts, percentages)
- Location on page (top/middle/bottom)
"""

    return prompt
