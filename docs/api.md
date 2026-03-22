# API (`api/generate.py`)

Flask application that exposes a single HTTP endpoint. Deployed as a Vercel serverless function.

## Endpoint

### `POST /api/generate`

Crawls a URL and returns a generated llms.txt document.

**Request body (JSON):**

```json
{
  "url": "https://example.com",
  "maxPages": 30
}
```

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `url` | string | Yes | — | Must start with `http://` or `https://` |
| `maxPages` | integer | No | `30` | Clamped to `[1, 100]`; non-integer values reset to default |

**Success response (200):**

```json
{
  "llmstxt": "# Site Name\n\n> Summary...\n\n## Section\n- [Page](url): desc\n"
}
```

**Error responses:**

| Status | Condition | Body |
|---|---|---|
| `400` | Missing or invalid URL | `{"error": "Invalid URL"}` |
| `405` | Non-POST, non-OPTIONS method | `{"error": "Method not allowed"}` |
| `422` | Crawl returned zero pages | `{"error": "Could not fetch any pages from <url>"}` |
| `500` | Unhandled exception in crawl or LLM/format step | `{"error": "Internal server error"}` |

**CORS:** All responses include `Access-Control-Allow-Origin: *`. `OPTIONS` requests return `204` with appropriate preflight headers.

## Processing steps

1. Parse and validate the request body.
2. Run `src.crawler.crawl(url, max_pages=max_pages)` via `asyncio.run` (the Flask handler is sync; the crawler is async).
3. If no pages were returned, respond with 422.
4. Run `src.llm.llm_process_pages(pages, url)` to enrich the pages.
5. Run `src.formatter.generate_llms_txt(...)` to produce the Markdown.
6. Return the result as JSON.

Exceptions from the crawl step and from the enrich/format step are caught separately so that errors from one don't mask errors from the other.

## Vercel wiring

`api/app.py` re-exports the `app` object:

```python
from api.generate import app
__all__ = ["app"]
```

Vercel detects this as a WSGI application. `vercel.json` rewrites `/api/generate` → `/api/generate.py` so the serverless function is invoked at the right path.

The `public/` directory is served as static files by Vercel's CDN. `GET /` redirects to `/index.html` via Flask, which the CDN serves.

## Local development

```bash
# Using Vercel dev (mirrors production routing and static file serving)
npx vercel dev

# Using Flask directly (no static file serving from public/)
flask --app api.generate run
```

With Flask directly, access the API at `http://localhost:5000/api/generate`. The frontend won't be served — use a browser extension or curl to test the endpoint.
