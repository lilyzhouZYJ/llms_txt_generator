"""Single OpenAI batch call to enrich crawled page metadata; rule-based fallback on failure."""

from __future__ import annotations

import json
import os
import re
import traceback

from openai import OpenAI

from src.prompts import ENRICH_SYSTEM_PROMPT, SECTION_REFINE_SYSTEM_PROMPT
from src.url_utils import netloc_from_http_url, normalize_http_url

DEFAULT_MODEL = "gpt-4o-mini"
ENV_API_KEY = "OPENAI_API_KEY"
ENV_MODEL = "OPENAI_MODEL"

# When there are no pages or no usable root title (should not happen after a normal crawl).
FALLBACK_SITE_NAME = "Unknown Website"

def _get_openai_client() -> OpenAI:
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        raise ValueError(f"{ENV_API_KEY} is not set")
    return OpenAI(api_key=api_key)

def _parse_json_content(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text, count=1)
    return json.loads(text)

########################################################
# Helpers for using LLM to generate page summaries
########################################################

def _build_summarize_pages_prompt(pages: list[dict], base_url: str) -> str:
    payload = [
        {
            "url": p["url"],
            "title": p.get("title", ""),
            "main_text": (p.get("main_text") or "")[:4000],
        }
        for p in pages
    ]
    return (
        f"The crawl started at: {base_url}\n\n"
        "Pages (JSON array):\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

def _update_pages_with_llm_summaries(orig_pages: list[dict], llm_data: dict) -> list[dict]:
    """
    Update the original pages with the new titles and descriptions from the LLM data.
    """
    llm_pages = llm_data.get("pages")
    if not isinstance(llm_pages, list):
        raise ValueError("response.pages must be a list")

    by_url: dict[str, dict] = {}
    for lp in llm_pages:
        if isinstance(lp, dict) and lp.get("url"):
            by_url[normalize_http_url(str(lp["url"]))] = lp

    # create a new updated_pages list; populate it with llm_data's titles and descriptions
    updated_pages: list[dict] = []
    for p in orig_pages:
        key = normalize_http_url(p["url"])
        lp = by_url.get(key)
        row = dict(p)
        if lp:
            if "title" in lp and lp["title"] is not None:
                row["title"] = str(lp["title"]).strip()
            if "description" in lp and lp["description"] is not None:
                row["description"] = str(lp["description"]).strip()
        updated_pages.append(row)
    return updated_pages

########################################################
# Helpers for using LLM to refine sections
########################################################

def _build_section_refine_prompt(
    pages: list[dict],
    base_url: str,
    site_name: str,
    site_summary: str,
) -> str:
    payload = [
        {
            "url": p["url"],
            "title": p.get("title", ""),
            "description": (p.get("description") or "")[:500],
            "section": p.get("section", ""),
            "section_hint": p.get("section_hint", ""),
        }
        for p in pages
    ]
    meta = {
        "site_name": site_name,
        "site_summary": (site_summary or "")[:1500],
        "base_url": base_url,
        "pages": payload,
    }
    return json.dumps(meta, ensure_ascii=False)

def _complete_section_order(section_order: list[str], sections_used: set[str]) -> list[str]:
    """
    Clean up LLM-generated section_order to make sure it contains every section that appear on
    at least one page and that it doesn't contain duplicates.
    """
    out: list[str] = []
    seen: set[str] = set()
    for s in section_order:
        s = s.strip()
        if s and s in sections_used and s not in seen:
            out.append(s)
            seen.add(s)

    # Sections that appear on at least one page but did not appear in the LLM-generated
    # section_order; append them in alphabetical order.
    remaining = sections_used - seen
    for s in sorted(remaining):
        out.append(s)
        seen.add(s)
    return out

def _update_pages_with_llm_sections(orig_pages: list[dict], llm_data: dict) -> tuple[list[dict], list[str]]:
    """
    Update the original pages with the new sections from the LLM data.
    """
    llm_pages = llm_data.get("pages")
    if not isinstance(llm_pages, list):
        raise ValueError("response.pages must be a list")

    by_url: dict[str, str] = {}
    for lp in llm_pages:
        if isinstance(lp, dict) and lp.get("url") and lp.get("section") is not None:
            by_url[normalize_http_url(str(lp["url"]))] = str(lp["section"]).strip()

    # create a new updated_pages list; populate it with llm_data's sections
    updated_pages: list[dict] = []
    for p in orig_pages:
        row = dict(p)
        key = normalize_http_url(p["url"])
        if key in by_url:
            row["section"] = by_url[key]
        updated_pages.append(row)

    # check which sections actually appear in the updated_pages list;
    # if section is empty, use "Pages" as default
    sections_used: set[str] = set()
    for row in updated_pages:
        name = str(row.get("section") or "Pages").strip() or "Pages"
        sections_used.add(name)

    # clean up any potential noise from the LLM-generated section order
    llm_section_order = llm_data.get("section_order")
    section_order: list[str] = []
    if isinstance(llm_section_order, list):
        for s in llm_section_order:
            if not s:
                # skip empty section names
                continue
            stripped = str(s).strip()
            if stripped:
                section_order.append(stripped)

    # make sure the section_order contains every section that exists
    section_order = _complete_section_order(section_order, sections_used)
    return updated_pages, section_order

########################################################
# Entry points for using LLM to (1) generate page summaries and (2) refine sections
########################################################

def llm_generate_page_summaries(pages: list[dict], base_url: str, client: OpenAI | None = None) -> dict:
    """
    Uses LLM to generate site_name, site_summary, as well as titles and descriptions for each page.
    """
    print(f"[llm_generate_page_summaries] processing {len(pages)} pages for website: {base_url}")
    if not pages:
        raise ValueError("pages is empty")

    user_message = _build_summarize_pages_prompt(pages, base_url)
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL

    openai_client = client if client is not None else _get_openai_client()
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ENRICH_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")
    print(f"[llm_generate_page_summaries] received model response")

    # parse llm response and update pages with the new titles and descriptions
    data = _parse_json_content(content)
    updated_pages = _update_pages_with_llm_summaries(pages, data)

    site_name = str(data.get("site_name") or "").strip()
    site_summary = str(data.get("site_summary") or "").strip()
    if not site_name:
        raise ValueError("missing site_name in model response")

    return {
        "site_name": site_name,
        "site_summary": site_summary,
        "pages": updated_pages,
    }

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
    print(f"[llm_refine_sections] processing {len(pages)} pages for website: {base_url}")
    if not pages:
        raise ValueError("pages is empty")

    user_message = _build_section_refine_prompt(pages, base_url, site_name, site_summary)
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL

    openai_client = client if client is not None else _get_openai_client()
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SECTION_REFINE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")
    print(f"[llm_refine_sections] received model response")

    data = _parse_json_content(content)

    # update pages with new LLM-generated sections;
    # also returns the new section order
    return _update_pages_with_llm_sections(pages, data)

########################################################
# Fallback to rule-based sectioning if the LLM calls fail
########################################################

def _find_root_page(pages: list[dict], base_url: str) -> dict | None:
    """
    Find the root page for the website.
    The root page is the page that is the base URL of the website.
    """
    target = normalize_http_url(base_url)
    for p in pages:
        if normalize_http_url(str(p["url"])) == target:
            return p
    return None

def _rule_based_fallback(pages: list[dict], base_url: str) -> tuple[list[dict], str, str]:
    """
    Fallback to rule-based sectioning if the LLM calls fail.
    Returns (pages, site_name, site_summary).
    Each page contains url, title, description, and its assigned section.
    The site_name is the title of the root page, fallback to the domain name.
    The site_summary is the description of the root page, fallback to an empty string.
    """
    root_page = _find_root_page(pages, base_url)
    if root_page:
        site_name = (root_page.get("title") or "").strip() or FALLBACK_SITE_NAME
        site_summary = (root_page.get("description") or "").strip()
    else:
        # No page matched base_url; use host from URL (e.g. example.com) for site_name.
        site_name = netloc_from_http_url(base_url) or FALLBACK_SITE_NAME
        site_summary = ""
    return pages, site_name, site_summary

########################################################
# Entry point for processing pages
########################################################

def llm_process_pages(pages: list[dict], base_url: str) -> tuple[list[dict], str, str, list[str] | None]:
    """
    Process crawled pages using LLM.
    This makes two LLM calls:
    (1) produce site_name, site_summary, and a list of pages with titles and descriptions for each
    (2) produce a list of sections and order the sections based on relevance

    Returns (pages, site_name, site_summary, section_order).
    Each page contains url, title, description, and its assigned section.
    """
    if not pages:
        # this is NOT expected since the homepage should always be crawled
        raise ValueError("pages is empty")

    for p in pages:
        p.setdefault("section_hint", p.get("section", ""))

    try:
        # (1) generate site_name, site_summary, and titles and descriptions for each page
        data = llm_generate_page_summaries(pages, base_url)
        pages_out = data["pages"]
        site_name = data["site_name"]
        site_summary = data["site_summary"]

        # (2) refine the sections and order them based on relevance
        section_order: list[str] | None
        try:
            pages_out, order = llm_refine_sections(
                pages_out,
                base_url,
                site_name,
                site_summary,
            )
            section_order = order
        except Exception:
            traceback.print_exc()
            section_order = None
        return pages_out, site_name, site_summary, section_order
    except Exception:
        traceback.print_exc()
        pages_out, site_name, site_summary = _rule_based_fallback(pages, base_url)
        return pages_out, site_name, site_summary, None
