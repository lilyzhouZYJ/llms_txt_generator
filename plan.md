# Implementation Plan: Automated llms.txt Generator

## Stack Summary
- **Backend / Crawler:** Python, Flask, BeautifulSoup4, httpx
- **LLM:** OpenAI Chat Completions API (single batch JSON call per website; rule-based fallback if it fails)
- **Sections (hybrid):** URL-derived `section` on each page is a **hint / prior** from `extractor.py`. The LLM assigns the **final** section labels for all pages in one request (global consistency: merge synonyms, fix misleading paths). If the LLM call fails, output uses extractor fields as-is.
- **Testing:** pytest
- **Frontend:** Vanilla HTML + CSS + JavaScript (no framework)
- **Deployment:** Vercel (Python serverless functions + static frontend)
- **Repo layout:** Monorepo

---

## Directory Structure (target)

```
llms_txt_generator/
├── api/
│   └── generate.py          # Vercel Python serverless function (POST /api/generate)
├── src/
│   ├── __init__.py
│   ├── crawler.py           # HTTP fetching + link extraction
│   ├── extractor.py         # Per-page metadata + URL-based section *hints* (rule-based)
│   ├── llm.py               # Single batch OpenAI call + rule-based fallback
│   └── formatter.py         # llms.txt assembly
├── tests/
│   ├── conftest.py          # Shared fixtures (mock HTML pages, etc.)
│   ├── test_crawler.py
│   ├── test_extractor.py
│   ├── test_llm.py
│   └── test_formatter.py
├── public/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── vercel.json
├── requirements.txt
└── README.md
```

---

## Phase 1 — Project Skeleton

### Step 1.1 — Directory structure & virtual environment
- Create the directories above (empty, with `.gitkeep` where needed)
- Create and activate a Python virtual environment (`python -m venv .venv`)
- Add `.venv/` to `.gitignore`

### Step 1.2 — Dependencies
Install and pin in `requirements.txt`:
```
httpx          # async-capable HTTP client for fetching pages
beautifulsoup4 # HTML parsing
flask          # lightweight API server / Vercel handler
openai         # OpenAI API SDK (single batch LLM call)
pytest         # test runner
pytest-mock    # mocking in tests
respx          # mock httpx requests in tests
```

### Step 1.3 — vercel.json skeleton
```json
{
  "rewrites": [{ "source": "/api/(.*)", "destination": "/api/generate.py" }]
}
```
_(Will be refined in Phase 5.)_

---

## Phase 2 — Crawler Module (`src/crawler.py`)

### Step 2.1 — `fetch_page(url: str) -> str | None`
- Use `httpx` with a 10-second timeout
- Set a descriptive `User-Agent` header
- Follow redirects (up to 5 hops)
- Return the response text if `Content-Type` is `text/html` and status is 2xx
- Return `None` for any error (timeout, non-2xx, non-HTML)

### Step 2.2 — `get_internal_links(html: str, base_url: str) -> list[str]`
- Parse with BeautifulSoup4
- Find all `<a href>` tags
- Resolve relative URLs against `base_url` with `urllib.parse.urljoin`
- Filter to same-scheme + same-netloc only (no subdomains unless they match exactly)
- Strip fragments (`#...`) and query strings from URLs before deduplication
- Return a deduplicated list

### Step 2.3 — `crawl(start_url: str, max_pages: int = 30) -> list[dict]`
- BFS over internal links starting from `start_url`
- For each page: call `fetch_page`, then `get_internal_links`, then `extractor.extract_metadata`
- Skip URLs already visited or already queued
- Stop when `max_pages` is reached
- Return list of metadata dicts (one per successfully fetched page)
- Fetch up to 5 pages concurrently using `httpx.AsyncClient` + `asyncio.gather`

---

## Phase 3 — Extractor Module (`src/extractor.py`)

Rule-based, no LLM. Runs per-page during crawling. Output is consumed by `llm.py`.

**Section field:** `_infer_section(url)` produces a **cheap prior** (first path segment + keyword map). It is **not** treated as the final IA split—locales, product areas, and “reasonable” groupings often disagree with the first URL segment. The LLM reassigns sections in Phase 4 using the full page list; this value is the fallback when the LLM is unavailable.

### Step 3.1 — `_extract_main_text(html: str, max_chars: int = 3000) -> str`
- Remove tags that are boilerplate: `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, `<aside>`
- Get remaining visible text via `.get_text(separator=" ", strip=True)`
- Truncate to `max_chars` — this becomes the LLM input snippet

### Step 3.2 — `extract_metadata(html: str, url: str) -> dict`
Returns:
```python
{
  "url": str,
  "title": str,        # <title> or og:title, fallback to last URL path segment (humanized)
  "description": str,  # <meta name="description"> or og:description, fallback to ""
  "section": str,      # URL-based *hint* for LLM; final label comes from Phase 4 (or this if LLM fails)
  "main_text": str,    # stripped body text, max 3000 chars (for LLM input)
}
```

### Step 3.3 — `_infer_section(url: str) -> str`
Prior for the LLM, and standalone fallback. Uses `urlparse(url).path` with leading/trailing `/` stripped, then the first path segment (before any `/`). Rules applied in order:
1. If the stripped path is empty (root URL, e.g. `/` or no path) → `"Overview"`
2. If the first segment matches a known keyword (case-insensitive):
   - `blog`, `posts`, `articles`, `news` → `"Blog"`
   - `docs`, `documentation`, `guide`, `guides`, `reference` → `"Documentation"`
   - `api` → `"API Reference"`
   - `about`, `team`, `company` → `"About"`
3. Otherwise → `str.capitalize()` on that segment, e.g. `/pricing/plans` → `"Pricing"`, `/foo-bar` → `"Foo-bar"` (not title case)

### Step 3.4 — Tests (`tests/test_extractor.py`)
- `test_extracts_title_from_title_tag`
- `test_falls_back_to_og_title`
- `test_falls_back_to_url_path_when_no_title`
- `test_extracts_meta_description`
- `test_falls_back_to_og_description`
- `test_main_text_strips_nav_and_footer`
- `test_main_text_truncates_to_max_chars`
- `test_section_inference_root` → `"Overview"`
- `test_section_inference_blog`
- `test_section_inference_docs`
- `test_section_inference_unknown_segment` → capitalized first segment
- `test_section_inference_root_no_trailing_slash` → `"Overview"` (optional; same as root with slash)

---

## Phase 4 — LLM Enrichment Module (`src/llm.py`)

One OpenAI API call per website. Takes all rule-based page dicts, returns enriched versions.

**Sectioning strategy**

- **Do:** Send structured fields per page (`url`, `title`, `description`, `section` hint, `main_text` snippet) in **one batched call** so the model can assign **consistent** section labels across the site (merge “API” vs “API Reference”, correct paths like `/learn/...` that are not “Learn” in a product sense).
- **Do:** Instruct the model to **reuse or override** the URL hint, merge near-duplicate headings, and cap the number of distinct sections (e.g. aim for **at most 6–8** H2-level groups unless the site is huge).
- **Optional tightening:** Ask for a normalized `section_key` from a small enum (`docs | blog | api | product | company | support | other`, etc.) and map keys to display strings—reduces duplicate H2s in `group_by_section`.
- **Don’t:** Rely on the LLM to “parse sections” from raw full HTML (noisy, expensive, brittle). Don’t use **per-page** LLM calls only for sectioning (inconsistent labels, higher cost/latency); one batch is enough for ≤50 pages.
- **Future optional:** Extract top-nav or breadcrumb labels from the root page HTML and pass them as extra hints in the prompt (better priors without an extra LLM call). Not required for the first implementation.

### Step 4.1 — `enrich_with_llm(pages: list[dict], start_url: str) -> dict`
Sends a **single** API call to OpenAI with a compact JSON payload of all pages:
```json
[
  { "url": "...", "title": "...", "description": "...", "section": "...", "main_text": "..." },
  ...
]
```
Asks the model to return:
```json
{
  "site_name": "...",
  "site_summary": "...",
  "pages": [
    { "url": "...", "title": "...", "description": "...", "section": "..." },
    ...
  ]
}
```
- Uses `openai` SDK with `chat.completions.create`, `response_format={"type": "json_object"}` (default model: `gpt-4o-mini`; override with `OPENAI_MODEL`)
- System + user prompts; response body parsed with `json.loads()` after optional markdown-fence stripping
- `OPENAI_API_KEY` read from environment variable (see `.env.example`); copy to `.env` or export in your shell
- Returned `section` per page is the **canonical** label for `formatter.group_by_section` (overwrites the extractor hint on success)

### Step 4.2 — `_build_prompt(pages: list[dict], start_url: str) -> str`
Constructs the user message. Each page entry includes url, title, existing description, **URL-inferred section (hint)**, and main_text snippet. Instructs the model to:
- Write a concise one-sentence description per page based on actual content (titles/meta alone may be wrong)
- **Sections:** Assign a **final** `section` string per page using **all pages as context**. Prefer short, human-readable H2-style names. Reuse the hint when it fits; **rename or merge** when the hint is misleading or duplicate (e.g. two labels meaning the same thing). Keep the **total number of distinct sections** small (give an explicit max in the prompt, e.g. 6–8)
- Derive `site_name` from the root page
- Write a 1–2 sentence `site_summary` describing the overall site

### Step 4.3 — `enrich_pages(pages: list[dict], start_url: str) -> tuple[list[dict], str, str]`
Top-level function called by the API layer. Returns `(enriched_pages, site_name, site_summary)`.
- Calls `enrich_with_llm()`; on any exception (API error, JSON parse failure, timeout) falls back to `_rule_based_fallback()`

### Step 4.4 — `_rule_based_fallback(pages: list[dict], start_url: str) -> tuple[list[dict], str, str]`
- `site_name`: title of first page (root), fallback to domain name
- `site_summary`: description of first page, fallback to `""`
- `pages`: returned as-is (extractor `section` hints and descriptions; no LLM merge of synonyms—acceptable degradation)

### Step 4.5 — Tests (`tests/test_llm.py`)
Mock `_get_openai_client()` / `client.chat.completions.create` (via `pytest-mock`) — no real API calls in tests:
- `test_enrich_pages_returns_llm_data_on_success` — mock returns valid JSON; check site_name, site_summary, descriptions are updated; **`section` values from mock replace extractor hints**
- `test_enrich_pages_falls_back_on_api_error` — mock raises exception; check fallback site_name = root page title; **sections remain extractor hints**
- `test_enrich_pages_falls_back_on_invalid_json` — mock returns malformed JSON; check fallback is used
- `test_rule_based_fallback_uses_root_page_title`
- `test_rule_based_fallback_uses_domain_when_no_root_page`

---

## Phase 5 — Formatter Module (`src/formatter.py`)

Pure data assembly — no HTTP, no LLM. Consumes output of `llm.enrich_pages()`.

### Step 5.1 — `group_by_section(pages: list[dict]) -> dict[str, list[dict]]`
- Group page dicts by their `"section"` key (after LLM enrichment, these are the **final** labels)
- Sort sections so `"Overview"` comes first, then alphabetically
- Within each section, preserve input order (BFS discovery order)

### Step 5.2 — `format_link_entry(page: dict) -> str`
- Returns `- [Title](url)` if no description
- Returns `- [Title](url): description` if description is non-empty
- Truncate description to 120 characters with `...` if needed

### Step 5.3 — `generate_llms_txt(pages: list[dict], site_name: str, site_summary: str) -> str`
Assembles the final file:
```
# {site_name}

> {site_summary}

## {Section}
- [Title](url): description
...

## {Section}
...
```
Omit blockquote line if `site_summary` is empty.

### Step 5.4 — Tests (`tests/test_formatter.py`)
- `test_group_by_section_overview_first`
- `test_group_by_section_alphabetical_after_overview`
- `test_format_link_entry_no_description`
- `test_format_link_entry_with_description`
- `test_format_link_entry_truncates_long_description`
- `test_generate_llms_txt_has_h1`
- `test_generate_llms_txt_has_blockquote_when_summary_present`
- `test_generate_llms_txt_omits_blockquote_when_no_summary` (failure/edge case)
- `test_generate_llms_txt_has_h2_sections`

---

## Phase 6 — API Layer (`api/generate.py`)

### Step 6.1 — Flask handler
```python
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route('/api/generate', methods=['POST'])
def generate():
    ...
```
Vercel invokes this as a serverless function.

### Step 6.2 — Request handling
- Parse JSON body: `{ "url": str, "maxPages": int (optional, default 30) }`
- Validate URL (must start with `http://` or `https://`; return 400 otherwise)
- Call `crawler.crawl(url, max_pages)` → list of raw page dicts
- If result is empty list → return 422 with `{ "error": "..." }`
- Call `llm.enrich_pages(pages, url)` → `(enriched_pages, site_name, site_summary)`
- Call `formatter.generate_llms_txt(enriched_pages, site_name, site_summary)`
- Return 200 with `{ "llmstxt": str }`

### Step 6.3 — Error responses
| Scenario | HTTP status | `error` message |
|---|---|---|
| Invalid URL | 400 | `"Invalid URL"` |
| Unreachable / all pages failed | 422 | `"Could not fetch any pages from <url>"` |
| Unexpected exception | 500 | `"Internal server error"` |

### Step 6.4 — CORS
- Add `Access-Control-Allow-Origin: *` header (needed for local dev; Vercel rewrites handle prod)

---

## Phase 7 — Frontend (`public/`)

### Step 7.1 — `index.html`
- URL input field + optional "Max pages" number input (collapsed by default, shown via "Advanced" toggle)
- "Generate" button
- Loading spinner (hidden by default)
- Output section (hidden until results arrive):
  - Read-only `<textarea>` showing the generated file
  - "Copy to clipboard" button
  - "Download llms.txt" button
- Error banner (hidden by default)

### Step 7.2 — `style.css`
- Centered single-column layout, max-width ~640px
- Mobile-responsive (no media query magic needed at this width)
- Clean, minimal — no external CSS framework required

### Step 7.3 — `app.js`
- On form submit: `fetch('/api/generate', { method: 'POST', body: JSON.stringify({url, maxPages}) })`
- Show spinner while waiting
- On success: populate textarea, show output section
- Copy button: `navigator.clipboard.writeText(...)`
- Download button: create a `<a download="llms.txt">` blob URL and click it programmatically
- On error: show error banner with message from API

---

## Phase 8 — Vercel Deployment

### Step 8.1 — Final `vercel.json`
```json
{
  "rewrites": [
    { "source": "/api/generate", "destination": "/api/generate.py" }
  ]
}
```

### Step 8.2 — Python runtime config
- Vercel auto-detects Python functions in `api/`. Add `api/requirements.txt` (or root-level) with pinned deps.
- Confirm Python version via `.python-version` file (`3.11`).

### Step 8.3 — Deploy & smoke test
- `vercel deploy --prod`
- Test with a known small site (e.g., `https://example.com`)
- Verify generated output is valid Markdown and spec-compliant

---

## Phase 9 — Documentation

### Step 9.1 — README.md
Sections:
1. Project description
2. Prerequisites (`python 3.11+`, `node` only needed for Vercel CLI)
3. Local setup (clone, venv, `pip install -r requirements.txt`, copy `.env.example` → `.env` and set `OPENAI_API_KEY`, `vercel dev`)
4. Running tests (`pytest`)
5. Deployment (`vercel deploy --prod`)
6. How the crawler works (brief prose)
7. How sections work: URL hints from the extractor, final labels from one batched LLM call (fallback = hints)
8. Example output snippet

### Step 9.2 — Screenshots
- Screenshot 1: input form
- Screenshot 2: generated output with copy/download buttons
- (Optional) short screen recording

---

## Order of Execution

```
Phase 1  → skeleton & deps                        ✓ done
Phase 2  → crawler.py + tests                     ✓ done
Phase 3  → extractor.py + tests                   ✓ done
Phase 4  → llm.py + tests                          ✓ done
Phase 5  → formatter.py + tests                   ✓ done
Phase 6  → api/generate.py                         ✓ done
Phase 7  → frontend
Phase 8  → deployment
Phase 9  → docs
```
