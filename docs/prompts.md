# LLM Prompts (`src/prompts.py`)

Defines the three system prompts used by the LLM enrichment pipeline. Each prompt corresponds to one of the three passes in `src/llm.py`.

## `LINKED_PAGES_SUMMARY_SYSTEM_PROMPT` — Pass 1

Used by `llm_generate_page_summaries`. Generates improved titles and concise descriptions for a batch of linked pages.

**Input format (user message):**
```json
{
  "base_url": "https://example.com",
  "pages": [
    {
      "url": "https://example.com/blog/post",
      "title": "My Post",
      "main_text": "..."
    }
  ]
}
```

**Output format:**
```json
{
  "pages": [
    {
      "url": "https://example.com/blog/post",
      "title": "My Post",
      "description": "A 1–2 sentence description derived from main_text."
    }
  ]
}
```

**Key rules the prompt enforces:**
- Fix titles only when they are clearly wrong or too generic (e.g. just the domain name).
- Write descriptions from the `main_text` content, not from meta tags or CTAs.
- Descriptions should be neutral and informative (1–2 sentences).
- Return an empty description for pages with minimal content rather than inventing one.
- Every URL in the input must appear exactly once in the output.

---

## `SITE_OVERVIEW_SYSTEM_PROMPT` — Pass 2

Used by `llm_generate_site_summary`. Generates the site name and a site-wide summary.

**Input format (user message):**
```json
{
  "base_url": "https://example.com",
  "homepage": {
    "url": "https://example.com/",
    "title": "Example",
    "main_text": "..."
  },
  "linked_pages": [
    {
      "url": "https://example.com/features",
      "title": "Features",
      "description": "LLM-generated description from pass 1."
    }
  ]
}
```

Note: `linked_pages` includes only `url`, `title`, and `description` — not `main_text`. The full `main_text` is only provided for the homepage.

**Output format:**
```json
{
  "site_name": "Example",
  "site_summary": "3–4 sentences describing the entire site."
}
```

**Key rules the prompt enforces:**
- `site_name` must be short and human-readable (not a URL).
- `site_summary` synthesizes the whole site's purpose from the homepage content and linked page descriptions — not just the homepage alone.
- Neutral and substantive; no marketing language or CTAs.

---

## `SECTION_REFINE_SYSTEM_PROMPT` — Pass 3

Used by `llm_refine_sections`. Re-assigns pages to section labels and determines the display order.

**Input format (user message):**
```json
{
  "site_name": "Example",
  "site_summary": "...",
  "base_url": "https://example.com",
  "pages": [
    {
      "url": "https://example.com/features/x",
      "title": "Feature X",
      "description": "...",
      "section": "Features"
    }
  ]
}
```

`section` is the URL-path-based hint from the extractor, which the LLM uses as a starting point before reassigning.

**Output format:**
```json
{
  "section_order": ["Features", "Solutions", "Resources", "About"],
  "pages": [
    {"url": "https://example.com/features/x", "section": "Features"}
  ]
}
```

**Key rules the prompt enforces:**
- Target 6–8 distinct section labels across the whole site (prevents fragmentation).
- Merge related labels (e.g. "Blog Posts" and "Articles" → "Blog").
- `section_order` lists sections most-important-first; it is used as the `##` heading order in the output.
- Every input URL must appear exactly once in `pages`.

---

## Design notes

All three prompts:
- Request JSON output with no Markdown code fences (the parser handles fences as a defensive measure, but the prompts ask the model not to include them).
- Use `temperature=0.2` to keep output deterministic and consistent.
- Use OpenAI's `response_format: {"type": "json_object"}` to guarantee valid JSON.
