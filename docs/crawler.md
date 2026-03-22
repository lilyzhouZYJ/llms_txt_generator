# Crawler (`src/crawler.py`)

Performs a breadth-first crawl of a website, fetching pages concurrently and extracting internal links. Returns a list of page metadata dicts ready for LLM enrichment.

## Configuration constants

| Constant | Value | Description |
|---|---|---|
| `USER_AGENT` | `"llms-txt-generator/1.0"` | Sent in the `User-Agent` header |
| `TIMEOUT` | `10.0` | Per-request timeout in seconds |
| `MAX_CONCURRENCY` | `5` | Max simultaneous in-flight HTTP requests |
| `MAX_CRAWL_DEPTH` | `2` | Maximum hop depth from the start URL (0 = start page, 1 = pages linked from it, 2 = pages linked from those) |

### Excluded path segments

URLs whose path contains any of these segments are silently skipped:

```
login  auth  admin  static  _next  cdn-cgi  cart  checkout
account  settings  terms  privacy-policy  cookie  sitemap
feed  rss  wp-  tag  category  page
```

This prevents crawling auth walls, CMS infrastructure, pagination, and purely navigational pages that add noise to the output.

## Public API

### `fetch_page(client, url) -> str | None`

Fetches a single URL using the provided `httpx.AsyncClient` and returns the response body as a string. Returns `None` if:

- The HTTP status code is not 2xx
- The `Content-Type` is not `text/html`
- Any exception is raised (network error, timeout, etc.)

The client is passed in rather than created per call so that a single TCP connection pool is reused across the crawl.

### `is_allowed_url(url, start_url) -> bool`

Returns `True` if the URL is safe to crawl. Checks:

1. Scheme must be `http` or `https`
2. Domain must be the same as or a subdomain of `start_url`'s domain (e.g. `blog.example.com` is allowed when start is `example.com`)
3. No path segment may appear in `EXCLUDED_PATH_SEGMENTS`

### `get_internal_links(html, page_url, start_url) -> list[str]`

Parses all `<a href>` attributes from `html`, resolves them to absolute URLs relative to `page_url`, filters through `is_allowed_url`, normalizes them, and returns a deduplicated list. Skips `mailto:`, `tel:`, `javascript:`, and bare fragment (`#`) hrefs.

### `crawl(start_url, max_pages=30, max_crawl_depth=MAX_CRAWL_DEPTH) -> list[dict]`

The main entry point. Runs a BFS crawl starting from `start_url` and returns a list of page metadata dicts (as produced by `src/extractor.extract_metadata`).

**Parameters:**

- `start_url` — The seed URL. Normalized before use.
- `max_pages` — Hard cap on total pages fetched. Default 30, max 100 (enforced by the API layer).
- `max_crawl_depth` — Max hop distance from the start URL. Pages at depth > this are not enqueued.

**Algorithm:**

1. Initialize a queue with `(start_url, depth=0)` and an empty visited set.
2. Dequeue up to `MAX_CONCURRENCY` URLs and fetch them concurrently with `asyncio.gather`.
3. For each successful response, extract metadata (via `extract_metadata`) and discover links (via `get_internal_links`).
4. Enqueue newly discovered links at `depth + 1`, provided they haven't been visited and depth doesn't exceed `max_crawl_depth`.
5. Repeat until the queue is empty or `max_pages` is reached.

Pages for which `fetch_page` returns `None` (fetch failure, wrong content type, etc.) are silently skipped — they don't count toward `max_pages`.

## Interaction with other modules

- Calls `src.extractor.extract_metadata(html, url)` for each successfully fetched page.
- Calls `src.url_utils.normalize_http_url` for URL deduplication in the visited set and queue.
- Returns data consumed by `src.llm.llm_process_pages`.
