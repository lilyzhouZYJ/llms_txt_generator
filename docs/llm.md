# LLM Enrichment (`src/llm.py`)

Enriches crawled page metadata through three sequential LLM passes. Includes batching, parallelism, and comprehensive fallback logic.

## Configuration

| Constant | Default | Env override | Description |
|---|---|---|---|
| `DEFAULT_MODEL` | `gpt-4o-mini` | `OPENAI_MODEL` | OpenAI model used for all calls |
| `PAGES_PER_LLM_REQUEST` | `6` | — | Pages per batch in the page-summary pass |
| `MAIN_TEXT_CHARS_PER_PAGE` | `4000` | — | Max `main_text` characters sent per page |
| `MAX_PARALLEL_WORKERS` | `8` | — | Thread pool size cap for parallel batches |
| `FALLBACK_SITE_NAME` | `"Unknown Website"` | — | Used when root page has no title |

## Entry point

### `llm_process_pages(pages, base_url, parallel=True) -> (list[dict], str, str, list[str] | None)`

Orchestrates the full enrichment pipeline. Takes the raw crawler output and returns:

```
(enriched_linked_pages, site_name, site_summary, section_order)
```

- `enriched_linked_pages` — linked pages only (homepage excluded); each dict has LLM-generated `title`, `description`, and `section`.
- `site_name` — short human-readable site name.
- `site_summary` — 3–4 sentence description of the whole site.
- `section_order` — ordered list of section names for the formatter, or `None` if section refinement failed.

**The homepage is always excluded from the returned pages.** It provides the site name/summary (the document header in llms.txt) rather than appearing as a link entry.

## The three passes

### Pass 1 — Page summaries

**Function:** `llm_generate_page_summaries(pages, base_url, client=None, parallel=True)`

Generates an improved `title` and a concise `description` for each linked page from its `main_text`. Only linked pages are processed; the homepage is handled separately in pass 2.

**Batching:** Pages are split into batches of `PAGES_PER_LLM_REQUEST` (6). Each batch is a separate API call so large sites don't overflow the context window.

**Parallelism:** When `parallel=True` and there are multiple batches, all batches are submitted to a `ThreadPoolExecutor` simultaneously. Each thread creates its own `OpenAI` client instance because `httpx.Client` (used internally by the SDK) is not thread-safe. Results are collected in order using a `batch_results` list indexed by batch position.

The raw LLM output for each batch is a JSON object `{"pages": [...]}`. After all batches complete, `_update_pages_with_llm_summaries` overlays the new `title` and `description` onto the original page dicts (matched by normalized URL), preserving any fields the LLM didn't return.

**Prompt:** `LINKED_PAGES_SUMMARY_SYSTEM_PROMPT` (see `src/prompts.py`).

---

### Pass 2 — Site overview

**Function:** `llm_generate_site_summary(homepage, linked_pages, base_url, client=None) -> (str, str)`

Generates the site name and a multi-sentence summary of the entire site. This pass runs **after** page summaries complete so it can use the enriched descriptions for the linked pages, giving the LLM a better picture of what the site covers.

The prompt sends:
- The full homepage content (`url`, `title`, `main_text` up to `MAIN_TEXT_CHARS_PER_PAGE` chars)
- A lightweight list of linked pages (`url`, `title`, `description` only — no `main_text`)

The LLM returns `{"site_name": "...", "site_summary": "..."}`. A missing or empty `site_name` raises a `ValueError`, triggering the full fallback.

**Prompt:** `SITE_OVERVIEW_SYSTEM_PROMPT`.

---

### Pass 3 — Section refinement (optional)

**Function:** `llm_refine_sections(pages, base_url, site_name, site_summary, client=None) -> (list[dict], list[str])`

Re-assigns each linked page to a section and returns a preferred section ordering. The prompt receives each page's current URL-path-based `section` so the LLM can use it as a starting point.

The LLM returns:
```json
{
  "section_order": ["Features", "Solutions", "Resources", ...],
  "pages": [
    {"url": "...", "section": "Features"},
    ...
  ]
}
```

`_update_pages_with_llm_sections` overlays the new `section` value onto each page. `_complete_section_order` deduplicates the returned order list and appends any sections that appear in the pages but weren't listed by the LLM.

**This pass is wrapped in its own try/except.** If it fails (bad JSON, network error, etc.), enrichment continues with the pass 1–2 results and `section_order = None`. The formatter falls back to alphabetical section ordering.

**Prompt:** `SECTION_REFINE_SYSTEM_PROMPT`.

---

## Fallback behavior

The outer `try` block in `llm_process_pages` catches any exception from passes 1 or 2. On failure:

1. `_rule_based_fallback` extracts `site_name` and `site_summary` from the root page's extractor-generated title/description (or from the URL's `netloc` if the root page wasn't found).
2. `_split_root_and_linked` separates the homepage from the linked pages.
3. The function returns the unmodified linked pages (with only extractor data), the fallback site name/summary, and `section_order = None`.

This means a working output is always produced — the result is just less polished than when LLM enrichment succeeds.

## URL normalization

All URL matching throughout this module uses `src.url_utils.normalize_http_url` (lowercase scheme/host, strip query/fragment, normalize trailing slash). This ensures pages are correctly matched even if the crawler saw slightly different URL forms.

## All public functions

| Function | Returns | Description |
|---|---|---|
| `llm_process_pages(pages, base_url, parallel)` | `(list[dict], str, str, list[str]\|None)` | Main entry point; orchestrates all three passes with fallback |
| `llm_generate_page_summaries(pages, base_url, client, parallel)` | `list[dict]` | Pass 1: generate per-page title/description |
| `llm_generate_site_summary(homepage, linked_pages, base_url, client)` | `(str, str)` | Pass 2: generate site_name and site_summary |
| `llm_refine_sections(pages, base_url, site_name, site_summary, client)` | `(list[dict], list[str])` | Pass 3: assign sections and return section ordering |
