# Extractor (`src/extractor.py`)

Rule-based extraction of structured metadata from raw HTML. Called once per page during the crawl; its output serves both as input to the LLM enrichment passes and as the fallback data if LLM calls fail.

## Public API

### `extract_metadata(html, url) -> dict`

The sole public function. Parses `html` and returns:

```python
{
    "url":         str,   # the URL passed in, unchanged
    "title":       str,   # page title
    "description": str,   # short description
    "section":     str,   # inferred section label
    "main_text":   str,   # stripped body text (max 3000 chars)
}
```

### Title extraction (priority order)

1. The `<title>` element inside `<head>` — but **not** a `<title>` that is a descendant of `<svg>` or `<math>`. Inline SVG logos embedded in the page body often have their own `<title>` tags, which would otherwise be picked up ahead of the real document title.
2. The `og:title` meta property.
3. The last non-empty path segment of the URL, capitalized, with hyphens and underscores replaced by spaces (e.g. `/blog/my-first-post` → `"My first post"`).

### Description extraction (priority order)

1. `<meta name="description" content="...">`
2. `<meta property="og:description" content="...">`
3. Empty string if neither is present.

### Section inference

Derived from the **first** path segment of the URL by looking it up in a built-in map:

| Path segment | Section label |
|---|---|
| `blog` | Blog |
| `docs` | Documentation |
| `api` | API Reference |
| `guides` | Guides |
| `tutorials` | Tutorials |
| `reference` | Reference |
| `changelog` | Changelog |
| `about` | About |
| `pricing` | Pricing |
| `careers` | Careers |
| `press` | Press |
| `legal` | Legal |
| `support` | Support |
| `help` | Help |
| `community` | Community |
| `integrations` | Integrations |

If the path is `/` (root), the section is `"Home"`. Any segment not in the map is capitalized and used as-is (e.g. `/solutions/...` → `"Solutions"`).

This is later overridden by the LLM section-refinement pass.

### Main text extraction

Removes `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, and `<aside>` from the parsed tree, then calls BeautifulSoup's `.get_text(separator=" ")`. The result is stripped and truncated to **3000 characters**. This text is used only as LLM input and does not appear in the final output.

## Interaction with other modules

- Called by `src.crawler.crawl` immediately after each successful page fetch.
- The entire output dict is returned as-is by `_rule_based_fallback` when LLM enrichment fails.
