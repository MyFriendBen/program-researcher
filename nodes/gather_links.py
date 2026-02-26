"""
Node: Gather Links

Step 1 of the QA process - discover and catalog all documentation links.
"""

import json
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings
from ..prompts.researcher import RESEARCHER_PROMPTS
from ..state import (
    LinkCatalog,
    LinkCatalogEntry,
    LinkCategory,
    ResearchState,
    WorkflowStatus,
)
from ..tools.output_saver import save_fetched_content
from ..tools.web_research import (
    categorize_url,
    extract_legislative_citations,
    fetch_url,
)


async def gather_links_node(state: ResearchState) -> dict:
    """
    Gather and catalog all documentation links for the program.

    This node:
    1. Fetches each provided source URL
    2. Extracts links from the content
    3. Identifies legislative citations
    4. Categorizes and titles each link
    5. Returns a structured link catalog
    """
    messages = list(state.messages)
    messages.append(f"Starting link discovery for {state.program_name}...")

    # Collect all links
    all_links: list[LinkCatalogEntry] = []

    # First, add the provided source URLs
    for url in state.source_urls:
        category, source_type = categorize_url(url)
        all_links.append(
            LinkCatalogEntry(
                category=LinkCategory(category),
                title=f"[Provided] {url.split('/')[-1] or 'Source Document'}",
                url=url,
                source_type=source_type,
                found_in="Provided",
                accessible=True,  # Will verify below
            )
        )

    # Fetch each source and extract links
    # Save fetched content to files and track file paths
    fetched_content_refs: dict[str, str] = {}

    for index, url in enumerate(state.source_urls):
        messages.append(f"Fetching {url}...")
        result = await fetch_url(url)

        if not result.success:
            messages.append(f"  Warning: Failed to fetch {url}: {result.error}")
            # Mark as inaccessible
            for link in all_links:
                if link.url == url:
                    link.accessible = False
            continue

        # Save content to file
        if state.output_dir:
            from pathlib import Path
            output_dir = Path(state.output_dir)
            filepath = save_fetched_content(output_dir, url, result.content, index)
            fetched_content_refs[url] = str(filepath)
            messages.append(f"  Saved content to {filepath.name}")

        messages.append(f"  Found {len(result.links)} links in {url}")

        # Add discovered links
        for link_data in result.links:
            href = link_data["href"]
            text = link_data["text"]

            # Skip if we already have this URL
            if any(l.url == href for l in all_links):
                continue

            category, source_type = categorize_url(href, text)
            all_links.append(
                LinkCatalogEntry(
                    category=LinkCategory(category),
                    title=text or href.split("/")[-1],
                    url=href,
                    source_type=source_type,
                    found_in=f"Referenced in {url.split('/')[-1]}",
                    accessible=True,  # Assume accessible for now
                )
            )

        # Extract legislative citations from content
        citations = extract_legislative_citations(result.content)
        for citation in citations:
            # Skip if we already have this
            if any(l.url == citation["url"] for l in all_links):
                continue

            all_links.append(
                LinkCatalogEntry(
                    category=LinkCategory.LEGISLATION
                    if "Law" in citation["type"]
                    else LinkCategory.REGULATION,
                    title=citation["citation"],
                    url=citation["url"],
                    source_type=citation["type"],
                    found_in=f"Cited in {url.split('/')[-1]}",
                    accessible=True,
                )
            )

    messages.append(f"Total links discovered: {len(all_links)}")

    # Use LLM to enhance titles and summaries
    # Load content from files for enhancement
    if fetched_content_refs and settings.anthropic_api_key:
        messages.append("Enhancing link metadata with AI...")
        from pathlib import Path

        # Load content from files temporarily for enhancement
        fetched_content_for_enhancement = {}
        for url, filepath in fetched_content_refs.items():
            try:
                fetched_content_for_enhancement[url] = Path(filepath).read_text(encoding='utf-8')
            except Exception as e:
                messages.append(f"  Warning: Could not load {filepath} for enhancement: {e}")

        enhanced_links = await enhance_links_with_llm(
            all_links, fetched_content_for_enhancement, state.program_name, state.state_code
        )
        if enhanced_links:
            all_links = enhanced_links

    # Build catalog
    catalog = LinkCatalog(
        program_name=state.program_name,
        state_code=state.state_code,
        research_date=date.today(),
        sources_provided=len(state.source_urls),
        links=all_links,
    )

    messages.append(f"Link catalog complete: {len(catalog.links)} links in {len(set(l.category for l in catalog.links))} categories")

    return {
        "link_catalog": catalog,
        "fetched_content_refs": fetched_content_refs,  # File paths for extract_criteria to use
        "messages": messages,
    }


async def enhance_links_with_llm(
    links: list[LinkCatalogEntry],
    content: dict[str, str],
    program_name: str,
    state_code: str,
) -> list[LinkCatalogEntry] | None:
    """Use LLM to enhance link titles and add content summaries."""
    try:
        llm = ChatAnthropic(
            model=settings.researcher_model,
            temperature=settings.model_temperature,
            max_tokens=settings.model_max_tokens,
            max_retries=settings.model_max_retries,
            api_key=settings.anthropic_api_key,
        )

        # Prepare context
        links_json = [
            {
                "url": link.url,
                "current_title": link.title,
                "category": link.category.value if isinstance(link.category, LinkCategory) else link.category,
                "found_in": link.found_in,
            }
            for link in links[:30]  # Limit to first 30 to avoid token limits
        ]

        prompt = f"""Review these links related to the {program_name} program in {state_code}.

For each link, provide:
1. A better descriptive title (include citation numbers for legislation)
2. A brief 1-sentence content summary if you can infer it

Links to review:
{json.dumps(links_json, indent=2)}

Available source content for reference:
{list(content.keys())}

Return a JSON array with the same structure, adding "enhanced_title" and "content_summary" fields:
```json
[
  {{"url": "...", "enhanced_title": "Better Title - Citation", "content_summary": "Brief description"}}
]
```

Only include entries you have meaningful improvements for."""

        response = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCHER_PROMPTS["system"]),
                HumanMessage(content=prompt),
            ]
        )

        # Parse response
        response_text = response.content
        if isinstance(response_text, list):
            response_text = response_text[0].get("text", "") if response_text else ""

        # Extract JSON from response
        json_match = response_text
        if "```json" in response_text:
            json_match = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_match = response_text.split("```")[1].split("```")[0]

        enhanced_data = json.loads(json_match)

        # Apply enhancements
        url_to_enhancement = {e["url"]: e for e in enhanced_data}
        for link in links:
            if link.url in url_to_enhancement:
                enhancement = url_to_enhancement[link.url]
                if "enhanced_title" in enhancement and enhancement["enhanced_title"]:
                    link.title = enhancement["enhanced_title"]
                if "content_summary" in enhancement:
                    link.content_summary = enhancement["content_summary"]

        return links

    except Exception as e:
        print(f"Warning: Failed to enhance links with LLM: {e}")
        return None
