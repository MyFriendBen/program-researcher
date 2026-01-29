"""
Web research tools for fetching and parsing documentation.

These tools handle:
- Fetching web pages
- Converting HTML to markdown/text
- Extracting links from pages
- Web search queries
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings


@dataclass
class FetchResult:
    """Result of fetching a URL."""

    url: str
    success: bool
    status_code: int | None
    content: str
    content_type: str
    links: list[dict[str, str]]  # {"text": ..., "href": ...}
    error: str | None = None


@dataclass
class SearchResult:
    """Result from a web search."""

    title: str
    url: str
    snippet: str


async def fetch_url(url: str, extract_links: bool = True) -> FetchResult:
    """
    Fetch a URL and optionally extract links.

    Args:
        url: The URL to fetch
        extract_links: Whether to extract links from HTML content

    Returns:
        FetchResult with content and extracted links
    """
    try:
        async with httpx.AsyncClient(
            timeout=settings.web_request_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BenefitsResearchBot/1.0; +https://myfriendben.org)"
            },
        ) as client:
            response = await client.get(url)

            content_type = response.headers.get("content-type", "")
            links: list[dict[str, str]] = []

            # Parse HTML content
            if "text/html" in content_type:
                soup = BeautifulSoup(response.text, "lxml")

                # Remove script and style elements
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                # Extract text content
                content = soup.get_text(separator="\n", strip=True)

                # Extract links if requested
                if extract_links:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        text = link.get_text(strip=True) or href

                        # Convert relative URLs to absolute
                        if href.startswith("/"):
                            href = urljoin(url, href)
                        elif not href.startswith(("http://", "https://", "mailto:", "tel:")):
                            href = urljoin(url, href)

                        # Only include http(s) links
                        if href.startswith(("http://", "https://")):
                            links.append({"text": text[:200], "href": href})

            # Handle PDF - return basic info
            elif "application/pdf" in content_type:
                content = f"[PDF Document - {len(response.content)} bytes]"

            # Plain text
            else:
                content = response.text

            return FetchResult(
                url=str(response.url),  # May differ from input if redirected
                success=True,
                status_code=response.status_code,
                content=content[:50000],  # Limit content size
                content_type=content_type,
                links=links[: settings.max_links_per_source],
            )

    except httpx.TimeoutException:
        return FetchResult(
            url=url,
            success=False,
            status_code=None,
            content="",
            content_type="",
            links=[],
            error="Request timed out",
        )
    except httpx.RequestError as e:
        return FetchResult(
            url=url,
            success=False,
            status_code=None,
            content="",
            content_type="",
            links=[],
            error=str(e),
        )


def extract_legislative_citations(text: str) -> list[dict[str, str]]:
    """
    Extract legislative citations from text and convert to URLs.

    Looks for:
    - U.S. Code: "42 U.S.C. § 1396" or "42 USC 1396"
    - CFR: "7 CFR Part 273" or "7 CFR § 273.9"
    - Public Laws: "P.L. 117-169" or "Public Law 117-169"
    - State statutes (varies by state)

    Returns:
        List of {"citation": ..., "url": ..., "type": ...}
    """
    citations = []

    # U.S. Code patterns
    usc_patterns = [
        r"(\d+)\s*U\.?S\.?C\.?\s*§?\s*(\d+[a-z]?(?:-\d+)?)",
        r"(\d+)\s+United\s+States\s+Code\s+(?:Section\s+)?(\d+[a-z]?)",
    ]
    for pattern in usc_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            title, section = match.groups()
            citations.append(
                {
                    "citation": f"{title} U.S.C. § {section}",
                    "url": f"https://uscode.house.gov/view.xhtml?req={title}+USC+{section}",
                    "type": "Federal Law",
                }
            )

    # CFR patterns
    cfr_patterns = [
        r"(\d+)\s*C\.?F\.?R\.?\s*(?:Part\s+)?(\d+(?:\.\d+)?)",
        r"(\d+)\s*C\.?F\.?R\.?\s*§\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in cfr_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            title, part = match.groups()
            # eCFR URL format
            part_num = part.split(".")[0]
            citations.append(
                {
                    "citation": f"{title} CFR Part {part}",
                    "url": f"https://www.ecfr.gov/current/title-{title}/part-{part_num}",
                    "type": "Federal Regulation",
                }
            )

    # Public Law patterns
    pl_patterns = [
        r"P\.?L\.?\s*(\d+)-(\d+)",
        r"Public\s+Law\s+(\d+)-(\d+)",
    ]
    for pattern in pl_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            congress, law_num = match.groups()
            citations.append(
                {
                    "citation": f"P.L. {congress}-{law_num}",
                    "url": f"https://www.congress.gov/public-laws/{congress}th-congress",
                    "type": "Public Law",
                }
            )

    # Colorado Revised Statutes
    crs_pattern = r"C\.?R\.?S\.?\s*§?\s*(\d+)-(\d+)-(\d+)"
    for match in re.finditer(crs_pattern, text, re.IGNORECASE):
        title, article, section = match.groups()
        citations.append(
            {
                "citation": f"C.R.S. § {title}-{article}-{section}",
                "url": f"https://leg.colorado.gov/colorado-revised-statutes",
                "type": "Colorado State Law",
            }
        )

    # Illinois Compiled Statutes
    ilcs_pattern = r"(\d+)\s*ILCS\s*(\d+)/(\d+(?:-\d+)?)"
    for match in re.finditer(ilcs_pattern, text, re.IGNORECASE):
        chapter, act, section = match.groups()
        citations.append(
            {
                "citation": f"{chapter} ILCS {act}/{section}",
                "url": f"https://www.ilga.gov/legislation/ilcs/ilcs.asp",
                "type": "Illinois State Law",
            }
        )

    # North Carolina General Statutes
    ncgs_pattern = r"N\.?C\.?G\.?S\.?\s*§?\s*(\d+[A-Z]?)-(\d+(?:\.\d+)?)"
    for match in re.finditer(ncgs_pattern, text, re.IGNORECASE):
        chapter, section = match.groups()
        citations.append(
            {
                "citation": f"N.C.G.S. § {chapter}-{section}",
                "url": f"https://www.ncleg.gov/Laws/GeneralStatuteSections/Chapter{chapter}",
                "type": "North Carolina State Law",
            }
        )

    # Deduplicate
    seen = set()
    unique_citations = []
    for c in citations:
        key = c["citation"].lower()
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return unique_citations


async def search_web(query: str, num_results: int = 10) -> list[SearchResult]:
    """
    Search the web for a query.

    Note: This is a placeholder. In production, you would integrate with
    a search API (Google Custom Search, Bing, SerpAPI, etc.)

    For now, returns empty list - the agent should use provided source URLs.
    """
    # TODO: Integrate with search API if needed
    # For the MVP, we rely on user-provided source URLs
    return []


def categorize_url(url: str, title: str = "") -> tuple[str, str]:
    """
    Categorize a URL based on its domain and path.

    Returns:
        Tuple of (category, source_type)
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    # Federal agencies
    if "fns.usda.gov" in domain:
        return "Official Program", "Federal Agency (USDA FNS)"
    if "usda.gov" in domain:
        return "Official Program", "Federal Agency (USDA)"
    if "hhs.gov" in domain or "cms.gov" in domain:
        return "Official Program", "Federal Agency (HHS)"
    if "ssa.gov" in domain:
        return "Official Program", "Federal Agency (SSA)"
    if "benefits.gov" in domain:
        return "Official Program", "Federal Benefits Portal"

    # Federal law/regulation
    if "uscode.house.gov" in domain or "law.cornell.edu" in domain:
        return "Legislation", "Federal Law"
    if "ecfr.gov" in domain or "federalregister.gov" in domain:
        return "Regulation", "Federal Regulation"
    if "congress.gov" in domain:
        return "Legislation", "Federal Legislation"

    # State agencies (general patterns)
    if ".gov" in domain and any(
        state in domain
        for state in [
            "colorado",
            "illinois",
            "northcarolina",
            "nc.",
            "il.",
            "co.",
            "mass",
            "ma.",
        ]
    ):
        if "leg" in domain or "statute" in path or "law" in path:
            return "Legislation", "State Law"
        if "admin" in path or "rule" in path or "code" in path:
            return "Regulation", "State Regulation"
        return "Official Program", "State Agency"

    # Research/Policy organizations
    if any(
        org in domain for org in ["cbpp.org", "urban.org", "kff.org", "ncsl.org", "clasp.org"]
    ):
        return "Research", "Policy Research"

    # Application portals
    if "apply" in path or "application" in path or "portal" in path:
        return "Application", "Application Portal"

    # Navigator/assistance
    if any(word in domain or word in path for word in ["help", "assist", "navigator", "foodbank"]):
        return "Navigator", "Local Assistance"

    # Default
    return "Research", "Other"


def is_government_source(url: str) -> bool:
    """Check if a URL is from a government domain."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return ".gov" in domain or ".mil" in domain
