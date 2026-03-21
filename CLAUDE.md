# CLAUDE.md

## Project Overview

An automated `llms.txt` generator. The user inputs a website URL; the tool crawls the site, extracts metadata, and returns a spec-compliant `llms.txt` file (per [llmstxt.org](https://llmstxt.org/)).

## Stack

| Layer | Technology |
|---|---|
| Crawler / Backend | Python 3.12, httpx, BeautifulSoup4 |
| LLM enrichment | OpenAI (`src/llm.py`), `OPENAI_API_KEY` (see `.env.example`) |
| API | Flask (Vercel Python serverless function) |
| Tests | pytest, pytest-mock, respx |
| Frontend | Vanilla HTML + CSS + JS (no framework) |
| Deployment | Vercel |

## Repo Layout

```
api/generate.py       # POST /api/generate — Vercel serverless entry point
src/crawler.py        # HTTP fetching, link extraction, BFS crawl loop
src/extractor.py      # Per-page metadata extraction and URL-based section hints
src/llm.py            # Single OpenAI batch call; rule-based fallback on failure
src/formatter.py      # llms.txt assembly from crawled page data
tests/                # pytest test suite
public/               # Static frontend (index.html, style.css, app.js)
requirements.txt      # Python dependencies
vercel.json           # Vercel routing config
.python-version       # Pins Python 3.12 (required for `vercel dev` / vercel-runtime)
```

## Implementation Plan

See `plan.md` for the full phase-by-phase breakdown. Phases are executed in this order:

1. Project skeleton (done)
2. `src/crawler.py` + tests
3. `src/extractor.py` + tests
4. `src/llm.py` + tests
5. `src/formatter.py` + tests
6. `api/generate.py`
7. Frontend (`public/`)
8. Vercel deployment
9. README + docs

## Testing Rules

- **Every phase that introduces logic must include unit tests written in the same phase.**
- Each test file must contain **at least one failure/error case** (e.g., bad input, network error, empty result, malformed HTML).
- Tests live in `tests/` and are run with:
  ```
  .venv/bin/pytest
  ```
- HTTP calls in tests are mocked with `respx` — no real network requests in the test suite.
- Do not use `unittest.mock.patch` to stub httpx; use `respx` fixtures instead.

## Key Conventions

- All crawler HTTP calls go through `httpx.AsyncClient`; the crawl entry point is an `async` function wrapped with `asyncio.run()` at the API boundary.
- Section inference lives exclusively in `src/extractor.py` — do not duplicate it elsewhere.
- The formatter must not import from `crawler.py` or `extractor.py`; it only consumes plain `dict` objects.
- Flask is used solely as a thin HTTP wrapper in `api/generate.py`; business logic stays in `src/`.
- Vercel looks for a Flask entry under `api/` (e.g. `api/app.py` re-exporting `app` from `api.generate`). Do not add a **root** `app.py` (wrong install context). Local API: `flask --app api.generate:app run` or `flask --app api.app:app run`.
