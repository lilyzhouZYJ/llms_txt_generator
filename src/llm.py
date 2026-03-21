"""Single OpenAI batch call to enrich crawled page metadata; rule-based fallback on failure."""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from openai import OpenAI

DEFAULT_MODEL = "gpt-4o-mini"
ENV_API_KEY = "OPENAI_API_KEY"
ENV_MODEL = "OPENAI_MODEL"

_SYSTEM_PROMPT = """You help build an llms.txt file for a website. You receive JSON for each crawled page: url, title, section_hint, and main_text (the actual visible body text of the page, stripped of nav/footer).

Respond with a single JSON object only (no markdown code fences, no commentary) with this shape:
{
  "site_name": string,
  "site_summary": string,
  "pages": [
    { "url": string, "title": string, "description": string, "section": string }
  ]
}

Rules:
- site_name: short name for the site, derived mainly from the root/start URL page when possible.
- site_summary: 1–2 sentences describing the whole site for the blockquote; base on the root page's main_text.
- For each input page, output one object with the same url. You may fix the title using main_text if the provided title is wrong or generic.
- section: final H2-style group name. Use all pages for consistency. Reuse the section_hint when it fits. Prefer at most 6–8 distinct sections.
- descriptions: **YOU MUST GENERATE THIS FROM main_text.** Do NOT copy or paraphrase the meta description from the page—that is usually marketing fluff. Read the main_text (the actual body content) and write a 1–2 sentence summary of what the page actually covers or explains. Be substantive and neutral. No CTAs like "Find out how...", "Learn how...". Prefer informative phrasing (e.g. "How Company X uses Modal for..." not "Find out how..."). Provide a description for every page when main_text has content; empty only for minimal pages (login form, redirect).
"""


def _normalize_url(url: str) -> str:
    p = urlparse(url)
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    path = (p.path or "/").rstrip("/") or "/"
    return f"{scheme}://{netloc}{path}"


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc
    return host if host else url


def _find_root_page(pages: list[dict], start_url: str) -> dict | None:
    target = _normalize_url(start_url)
    for p in pages:
        if _normalize_url(p["url"]) == target:
            return p
    return pages[0] if pages else None


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


def _build_prompt(pages: list[dict], start_url: str) -> str:
    payload = [
        {
            "url": p["url"],
            "title": p.get("title", ""),
            "section_hint": p.get("section", ""),
            "main_text": (p.get("main_text") or "")[:4000],
        }
        for p in pages
    ]
    return (
        f"The crawl started at: {start_url}\n\n"
        "Pages (JSON array):\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _merge_llm_into_pages(pages: list[dict], data: dict) -> list[dict]:
    llm_pages = data.get("pages")
    if not isinstance(llm_pages, list):
        raise ValueError("response.pages must be a list")

    by_url: dict[str, dict] = {}
    for lp in llm_pages:
        if isinstance(lp, dict) and lp.get("url"):
            by_url[_normalize_url(str(lp["url"]))] = lp

    merged: list[dict] = []
    for p in pages:
        key = _normalize_url(p["url"])
        lp = by_url.get(key)
        row = dict(p)
        if lp:
            if "title" in lp and lp["title"] is not None:
                row["title"] = str(lp["title"]).strip()
            if "description" in lp and lp["description"] is not None:
                row["description"] = str(lp["description"]).strip()
            if "section" in lp and lp["section"] is not None:
                row["section"] = str(lp["section"]).strip()
        merged.append(row)
    return merged


def enrich_with_llm(pages: list[dict], start_url: str, *, client: OpenAI | None = None) -> dict:
    """Call OpenAI once; return dict with site_name, site_summary, pages (merged list)."""
    print(f"[enrich_with_llm] starting with {len(pages)} pages, start_url: {start_url}")
    if not pages:
        return {"site_name": "", "site_summary": "", "pages": []}

    user_message = _build_prompt(pages, start_url)
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL

    openai_client = client if client is not None else _get_openai_client()
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty model response")

    data = _parse_json_content(content)
    print(f"[enrich_with_llm] model response: {json.dumps(data, ensure_ascii=False)}")
    merged_pages = _merge_llm_into_pages(pages, data)

    site_name = str(data.get("site_name") or "").strip()
    site_summary = str(data.get("site_summary") or "").strip()
    if not site_name:
        raise ValueError("missing site_name in model response")

    return {
        "site_name": site_name,
        "site_summary": site_summary,
        "pages": merged_pages,
    }


def _rule_based_fallback(pages: list[dict], start_url: str) -> tuple[list[dict], str, str]:
    root = _find_root_page(pages, start_url)
    if root:
        site_name = (root.get("title") or "").strip() or _domain_from_url(start_url)
        site_summary = (root.get("description") or "").strip()
    else:
        site_name = _domain_from_url(start_url)
        site_summary = ""
    return pages, site_name, site_summary


def enrich_pages(pages: list[dict], start_url: str) -> tuple[list[dict], str, str]:
    """Enrich crawled pages with OpenAI, or rule-based fallback on any failure."""
    if not pages:
        return [], _domain_from_url(start_url), ""

    try:
        data = enrich_with_llm(pages, start_url)
        return data["pages"], data["site_name"], data["site_summary"]
    except Exception:
        import traceback
        traceback.print_exc()
        return _rule_based_fallback(pages, start_url)
