# Architecture Overview

## What it does

The llms.txt generator accepts a website URL, crawls its pages, uses an LLM to enrich the metadata, and returns a spec-compliant [llms.txt](https://llmstxt.org/) Markdown file.

## Pipeline

```
User submits URL
      │
      ▼
┌─────────────┐
│  API layer  │  POST /api/generate (Flask, api/generate.py)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Crawler   │  BFS crawl up to N pages (src/crawler.py)
│             │  ← calls extract_metadata() per page (src/extractor.py)
└──────┬──────┘
       │  list[dict]  (url, title, description, section, main_text)
       ▼
┌─────────────────┐
│  LLM Enrichment │  Three sequential passes (src/llm.py)
│                 │  1. Page summaries — batch LLM calls, parallel
│                 │  2. Site overview  — single LLM call
│                 │  3. Section refine — single LLM call (optional)
└──────┬──────────┘
       │  list[dict]  (url, title, description, section) + site_name, site_summary, section_order
       ▼
┌─────────────┐
│  Formatter  │  Assembles llms.txt Markdown (src/formatter.py)
└──────┬──────┘
       │  string
       ▼
  JSON response  {"llmstxt": "..."}
```

## Data shape through the pipeline

Each page is a `dict` that gains fields as it moves through the pipeline:

| Field | Added by | Description |
|---|---|---|
| `url` | Crawler | Normalized page URL |
| `title` | Extractor | Rule-based title (may be overridden by LLM) |
| `description` | Extractor | Rule-based description (may be overridden by LLM) |
| `section` | Extractor | Inferred from URL path (may be overridden by LLM) |
| `section_hint` | `llm_process_pages` | Snapshot of the extractor's section, preserved for the section-refine prompt |
| `main_text` | Extractor | Stripped page body text (used for LLM input; not in final output) |

## Failure handling

The LLM enrichment layer has two levels of fallback:

- **Section refinement failure:** if the third LLM pass fails, the pipeline continues with the enriched titles/descriptions from passes 1–2 and `section_order = None` (sections are sorted alphabetically in the output).
- **Full LLM failure:** if any earlier pass fails, `llm_process_pages` catches the exception and returns the original rule-based metadata from `src/extractor.py`. The output is still valid — just less polished.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `api/generate.py` | HTTP handler, input validation, pipeline orchestration |
| `src/crawler.py` | BFS web crawl, link discovery, concurrent fetching |
| `src/extractor.py` | Rule-based HTML metadata extraction |
| `src/llm.py` | LLM calls, batching, parallelism, fallback logic |
| `src/prompts.py` | System prompts for each LLM pass |
| `src/formatter.py` | Assemble final llms.txt Markdown |
| `src/url_utils.py` | URL normalization and parsing |
| `public/app.js` | Browser UI, form handling, API calls |

## Deployment model

The app runs as a Vercel serverless function. `api/generate.py` is the entrypoint; `api/app.py` re-exports the Flask `app` for Vercel's WSGI detection. Static frontend files in `public/` are served by Vercel's CDN. The root route (`GET /`) redirects to `/index.html`.
