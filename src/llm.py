"""LLM calls to enrich crawled page metadata; rule-based fallback on failure."""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from src.prompts import (
    LINKED_PAGES_SUMMARY_SYSTEM_PROMPT,
    SECTION_REFINE_SYSTEM_PROMPT,
    SITE_OVERVIEW_SYSTEM_PROMPT,
)
from src.url_utils import netloc_from_http_url, normalize_http_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
PAGES_PER_LLM_REQUEST = 6
MAIN_TEXT_CHARS_PER_PAGE = 4000
MAX_PARALLEL_WORKERS = 8
ENV_API_KEY = "OPENAI_API_KEY"
ENV_MODEL = "OPENAI_MODEL"
FALLBACK_SITE_NAME = "Unknown Website"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        raise ValueError(f"{ENV_API_KEY} is not set")
    return OpenAI(api_key=api_key)

def _current_model() -> str:
    return os.environ.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL

def _parse_json_content(raw: str) -> dict:
    """
    Parse JSON from a model response, stripping optional markdown code fences.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text, count=1)
    return json.loads(text)

def _split_into_batches(items: list[dict], size: int) -> list[list[dict]]:
    """
    Split a list into batches of a given size.
    """
    return [items[i : i + size] for i in range(0, len(items), size)]

# ---------------------------------------------------------------------------
# Page list helpers
# ---------------------------------------------------------------------------

def _find_root_page(pages: list[dict], base_url: str) -> dict | None:
    """Return the page whose URL matches base_url, or None."""
    target = normalize_http_url(base_url)
    for p in pages:
        if normalize_http_url(str(p["url"])) == target:
            return p
    return None

def _pages_root_first(pages: list[dict], base_url: str) -> list[dict]:
    """Return pages with the root URL moved to front, preserving order for the rest."""
    target = normalize_http_url(base_url)
    root: dict | None = None
    rest: list[dict] = []
    for p in pages:
        if normalize_http_url(str(p["url"])) == target:
            root = p
        else:
            rest.append(p)
    return [root, *rest] if root is not None else list(pages)

def _split_root_and_linked(pages: list[dict], base_url: str) -> tuple[dict, list[dict]]:
    """Return (root_page, linked_pages). Falls back to first page as root if no URL match."""
    root = _find_root_page(pages, base_url)
    if root is not None:
        root_key = normalize_http_url(base_url)
        linked: list[dict] = []
        for p in pages:
            if normalize_http_url(str(p["url"])) != root_key:
                linked.append(p)
        return root, linked
    ordered = _pages_root_first(pages, base_url)
    if not ordered:
        raise ValueError("pages is empty")
    return ordered[0], ordered[1:]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_generate_page_summaries_prompt(
    pages: list[dict],
    base_url: str,
    batch_index: int,
    batch_total: int,
) -> str:
    cap = MAIN_TEXT_CHARS_PER_PAGE
    payload = [
        {
            "url": p["url"],
            "title": p.get("title", ""),
            "main_text": (p.get("main_text") or "")[:cap],
        }
        for p in pages
    ]
    return "\n".join([
        f"The crawl started at: {base_url}",
        f"This is batch {batch_index} of {batch_total}.",
        "",
        "Pages (JSON array):",
        json.dumps(payload, ensure_ascii=False),
    ])

def _build_site_overview_user_message(root: dict, linked_pages: list[dict], base_url: str) -> str:
    cap = MAIN_TEXT_CHARS_PER_PAGE
    body = {
        "base_url": base_url,
        "homepage": {
            "url": root["url"],
            "title": root.get("title", ""),
            "main_text": (root.get("main_text") or "")[:cap],
        },
        "linked_pages": [
            {
                "url": p["url"],
                "title": p.get("title", ""),
                "description": (p.get("description") or "")[:min(2000, cap)],
                "main_text": (p.get("main_text") or "")[:cap],
            }
            for p in linked_pages
        ],
    }
    return json.dumps(body, ensure_ascii=False)

def _build_section_refine_prompt(
    pages: list[dict],
    base_url: str,
    site_name: str,
    site_summary: str,
) -> str:
    meta = {
        "site_name": site_name,
        "site_summary": (site_summary or "")[:1500],
        "base_url": base_url,
        "pages": [
            {
                "url": p["url"],
                "title": p.get("title", ""),
                "description": (p.get("description") or "")[:500],
                "section": p.get("section", ""),
                "section_hint": p.get("section_hint", ""),
            }
            for p in pages
        ],
    }
    return json.dumps(meta, ensure_ascii=False)

# ---------------------------------------------------------------------------
# LLM response mergers
# ---------------------------------------------------------------------------

def _update_pages_with_llm_summaries(
    orig_pages: list[dict],
    llm_pages: list[dict]
) -> list[dict]:
    """
    Overlay LLM-generated title/description onto orig_pages.
    """
    # maps each URL to the LLM-generated page data
    by_url: dict[str, dict] = {}
    for lp in llm_pages:
        if isinstance(lp, dict) and lp.get("url"):
            key = normalize_http_url(str(lp["url"]))
            by_url[key] = lp
    updated_pages: list[dict] = []
    for p in orig_pages:
        orig_page = dict(p)
        llm_page = by_url.get(normalize_http_url(p["url"]))
        if llm_page:
            # update the original page
            if llm_page.get("title") is not None:
                orig_page["title"] = str(llm_page["title"]).strip()
            if llm_page.get("description") is not None:
                orig_page["description"] = str(llm_page["description"]).strip()
        updated_pages.append(orig_page)
    return updated_pages

def _complete_section_order(section_order: list[str], sections_used: set[str]) -> list[str]:
    """
    Deduplicate section_order and append any sections not present in the LLM list.
    """
    out: list[str] = []
    seen: set[str] = set()
    for s in section_order:
        s = s.strip()
        if s and s in sections_used and s not in seen:
            out.append(s)
            seen.add(s)
    for s in sorted(sections_used - seen):
        out.append(s)
    return out

def _update_pages_with_llm_sections(orig_pages: list[dict], llm_data: dict) -> tuple[list[dict], list[str]]:
    """
    Overlay LLM-assigned sections and return (updated_pages, ordered_section_names).
    """
    llm_pages = llm_data.get("pages")
    if not isinstance(llm_pages, list):
        raise ValueError("response.pages must be a list")

    # Map each URL to the LLM-assigned section label
    by_url: dict[str, str] = {}
    for lp in llm_pages:
        if isinstance(lp, dict) and lp.get("url") and lp.get("section") is not None:
            key = normalize_http_url(str(lp["url"]))
            by_url[key] = str(lp["section"]).strip()

    # Apply the LLM section to each page (keep original section if the URL wasn't returned)
    updated_pages: list[dict] = []
    for p in orig_pages:
        page = dict(p)
        key = normalize_http_url(p["url"])
        if key in by_url:
            page["section"] = by_url[key]
        updated_pages.append(page)

    # Collect the distinct section names that actually appear after the update
    sections_used: set[str] = set()
    for page in updated_pages:
        section = str(page.get("section") or "").strip() or "Pages"
        sections_used.add(section)

    # Extract the LLM's preferred section ordering, ignoring blank entries
    llm_section_order = llm_data.get("section_order")
    if not isinstance(llm_section_order, list):
        raise ValueError("response.section_order must be a list")
    section_order: list[str] = []
    for s in llm_section_order:
        s = str(s).strip()
        if s:
            section_order.append(s)

    return updated_pages, _complete_section_order(section_order, sections_used)


# ---------------------------------------------------------------------------
# LLM API calls
# ---------------------------------------------------------------------------

def llm_generate_site_summary(
    homepage: dict,
    linked_pages: list[dict],
    base_url: str,
    client: OpenAI | None = None,
) -> tuple[str, str]:
    """
    Use LLM to generate a site summary from the homepage and linked pages.
    Returns the site_name and site_summary.
    """
    logger.info("Generating site summary for %s (with %d linked pages)", base_url, len(linked_pages))
    if client is None:
        client = _get_client()

    response = client.chat.completions.create(
        model=_current_model(),
        messages=[
            {"role": "system", "content": SITE_OVERVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": _build_site_overview_user_message(homepage, linked_pages, base_url)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")

    data = _parse_json_content(content)
    site_name = str(data.get("site_name") or "").strip()
    site_summary = str(data.get("site_summary") or "").strip()
    if not site_name:
        raise ValueError("missing site_name in model response")

    logger.info("Site summary generation complete for %s: %s", base_url, site_name)
    return site_name, site_summary

def _llm_generate_page_summaries_batch(
    pages: list[dict],
    base_url: str,
    batch_index: int,
    batch_total: int,
    model: str,
    client: OpenAI,
) -> list[dict]:
    """
    Used by llm_generate_page_summaries in batch mode.
    Call the LLM for one batch of linked pages, to generate title and description for each page.
    
    Returns a list of the updated pages.
    Each page contains the generated title and description.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LINKED_PAGES_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": _build_generate_page_summaries_prompt(
                pages, base_url, batch_index, batch_total
            )},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")
    data = _parse_json_content(content)
    updated_pages = data.get("pages")
    if not isinstance(updated_pages, list):
        raise ValueError("response.pages must be a list")
    return updated_pages

def llm_generate_page_summaries(
    pages: list[dict],
    base_url: str,
    client: OpenAI | None = None,
    parallel: bool = True,
) -> list[dict]:
    """
    Generate LLM title + description for each linked page via batched calls.
    Batches run in parallel when parallel=True and there is more than one batch.
    """
    if not pages:
        return []
    logger.info("Generating page summaries: %d pages for %r", len(pages), base_url)

    model = _current_model()
    openai_client = client or _get_client()

    # split into batches
    batches = _split_into_batches(pages, PAGES_PER_LLM_REQUEST)
    n_batch = len(batches)
    updated_pages: list[dict] = []

    if n_batch > 1 and parallel:
        api_key = os.environ.get(ENV_API_KEY)
        if not api_key:
            raise ValueError(f"{ENV_API_KEY} is not set")

        def _run_batch(batch_index: int, batch: list[dict]) -> tuple[int, list[dict]]:
            # Each thread gets its own client — httpx.Client is not thread-safe
            per_thread_client = OpenAI(api_key=api_key)
            updated_batch = _llm_generate_page_summaries_batch(
                batch,
                base_url,
                batch_index=batch_index + 1,
                batch_total=n_batch,
                model=model,
                client=per_thread_client,
            )
            logger.info("Page summaries batch %d/%d complete", batch_index + 1, n_batch)
            return batch_index, updated_batch

        # stores the result of each batch
        batch_results: list[list[dict] | None] = [None] * n_batch

        # run batches in parallel
        with ThreadPoolExecutor(max_workers=min(n_batch, MAX_PARALLEL_WORKERS)) as pool:
            futures = [pool.submit(_run_batch, i, batch) for i, batch in enumerate(batches)]
            for fut in as_completed(futures):
                batch_index, updated_batch = fut.result()
                batch_results[batch_index] = updated_batch
        updated_pages = []
        for result in batch_results:
            if result is not None:
                for page in result:
                    updated_pages.append(page)
    else:
        # run batches sequentially
        for i, batch in enumerate(batches):
            updated_batch = _llm_generate_page_summaries_batch(
                batch,
                base_url,
                batch_index=i + 1,
                batch_total=n_batch,
                model=model,
                client=openai_client,
            )
            logger.info("Page summaries batch %d/%d complete", i + 1, n_batch)
            updated_pages.extend(updated_batch)

    if not updated_pages:
        # something went wrong
        raise ValueError("no updated pages")

    # update the pages with the LLM-generated title and description
    return _update_pages_with_llm_summaries(pages, updated_pages)

def llm_refine_sections(
    pages: list[dict],
    base_url: str,
    site_name: str,
    site_summary: str,
    client: OpenAI | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Uses LLM to refine the sections and order them based on relevance to the base website.
    Returns (updated_pages, section_order).
    Each page contains url, title, description, and its assigned section.
    The section_order is a list of section names in the order they should be displayed.
    """
    if not pages:
        raise ValueError("pages is empty")
    logger.info("Refining sections: %d pages for %r", len(pages), base_url)
    if client is None:
        client = _get_client()

    response = client.chat.completions.create(
        model=_current_model(),
        messages=[
            {"role": "system", "content": SECTION_REFINE_SYSTEM_PROMPT},
            {"role": "user", "content": _build_section_refine_prompt(pages, base_url, site_name, site_summary)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")

    logger.info("Section refinement complete")
    return _update_pages_with_llm_sections(pages, _parse_json_content(content))


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _rule_based_fallback(pages: list[dict], base_url: str) -> tuple[list[dict], str, str]:
    """
    Return rule-based (pages, site_name, site_summary) when LLM calls fail.
    """
    root_page = _find_root_page(pages, base_url)
    if root_page:
        site_name = (root_page.get("title") or "").strip() or FALLBACK_SITE_NAME
        site_summary = (root_page.get("description") or "").strip()
    else:
        site_name = netloc_from_http_url(base_url) or FALLBACK_SITE_NAME
        site_summary = ""
    return pages, site_name, site_summary

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def llm_process_pages(
    pages: list[dict],
    base_url: str,
    parallel: bool = True,
) -> tuple[list[dict], str, str, list[str] | None]:
    """
    Enrich crawled pages with LLM: titles/descriptions and section labels.
    Falls back to rule-based extractor data on any LLM failure.
    Returns (pages, site_name, site_summary, section_order).
    """
    if not pages:
        raise ValueError("pages is empty")

    for p in pages:
        p.setdefault("section_hint", p.get("section", ""))

    try:
        # split the pages into homepage and linked pages
        homepage, linked_pages = _split_root_and_linked(pages, base_url)

        if parallel:
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_linked = pool.submit(llm_generate_page_summaries, linked_pages, base_url, None, parallel)
                linked_pages_copy: list[dict] = []
                for p in linked_pages:
                    linked_pages_copy.append(dict(p))
                f_site = pool.submit(llm_generate_site_summary, dict(homepage), linked_pages_copy, base_url)
                linked_out = f_linked.result()
                site_name, site_summary = f_site.result()
        else:
            linked_out = llm_generate_page_summaries(linked_pages, base_url, parallel=False)
            site_name, site_summary = llm_generate_site_summary(homepage, linked_out, base_url)

        pages_out = [dict(homepage)] + linked_out

        try:
            pages_out, section_order = llm_refine_sections(pages_out, base_url, site_name, site_summary)
        except Exception:
            logger.exception("Section refinement failed; skipping")
            section_order = None

        return pages_out, site_name, site_summary, section_order

    except Exception:
        logger.exception("LLM enrichment failed; falling back to rule-based data")
        pages_out, site_name, site_summary = _rule_based_fallback(pages, base_url)
        return pages_out, site_name, site_summary, None
