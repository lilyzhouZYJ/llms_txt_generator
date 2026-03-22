# URL Utilities (`src/url_utils.py`)

Small utility module for consistent URL normalization and parsing. Used throughout the crawler and LLM enrichment layer to ensure URLs are compared and deduplicated reliably.

## Functions

### `normalize_http_url(url) -> str`

Normalizes a URL for use as a deduplication key or for equality comparison. Transformations applied:

- Lowercases the scheme and host.
- Defaults missing scheme to `https`.
- Strips the query string and fragment.
- Normalizes the path trailing slash: removes it everywhere except the root path `/` (which always has it).

Examples:

| Input | Output |
|---|---|
| `https://Example.com/path/` | `https://example.com/path` |
| `http://example.com/` | `http://example.com/` |
| `https://example.com/page?q=1#anchor` | `https://example.com/page` |
| `example.com/page` | `https://example.com/page` |

### `netloc_from_http_url(url) -> str`

Extracts and returns the lowercased `netloc` (authority) component of a URL — i.e. host, optional port, and optional userinfo. Uses `urllib.parse` rather than string splitting to handle edge cases like IPv6 addresses and non-standard ports correctly.

Used by `_rule_based_fallback` in `src/llm.py` to derive a site name from the URL when no root page title is available.

Examples:

| Input | Output |
|---|---|
| `https://example.com/path` | `example.com` |
| `https://sub.example.com:8080/` | `sub.example.com:8080` |
| `https://[::1]/path` | `[::1]` |
| `not-a-url` | `""` |

## Why a separate module

URL comparison appears in multiple places — the crawler's visited set, link deduplication, and the LLM layer's page matching. A single normalization function ensures that `https://Example.com/page/` and `https://example.com/page` are treated as the same URL everywhere, preventing both duplicate crawls and missed LLM result merges.
