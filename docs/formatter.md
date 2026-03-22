# Formatter (`src/formatter.py`)

Assembles the final llms.txt Markdown document from enriched page data, site name, and site summary.

## Output format

The generated file follows the [llms.txt spec](https://llmstxt.org/):

```markdown
# Site Name

> A short description of the site.

## Section One
- [Page Title](https://example.com/page): A concise description of this page.
- [Another Page](https://example.com/other)

## Section Two
- [Page](https://example.com/x): Description.
```

- The `#` heading is the site name.
- The `>` blockquote is the site summary. Omitted if empty.
- Each `##` heading is a section.
- Each link is `- [title](url)` or `- [title](url): description` (description omitted if empty).
- Descriptions longer than 500 characters are truncated with `...`.

## Public API

### `generate_llms_txt(pages, site_name, site_summary, section_order=None) -> str`

Assembles and returns the complete llms.txt document as a string (with a trailing newline).

- `pages` — list of enriched page dicts; each must have `url`, `title`, and optionally `description` and `section`.
- `site_name` — used as the `# H1` heading. Falls back to `"Untitled"` if empty.
- `site_summary` — used as the `> blockquote`. Skipped entirely if empty.
- `section_order` — if provided (from the LLM section-refinement pass), sections appear in this order; any section not listed is appended alphabetically. If `None`, all sections are sorted alphabetically.

### `group_by_section(pages, section_order=None) -> dict[str, list[dict]]`

Groups pages by their `section` field. Pages without a `section` are placed in `"Pages"`.

Returns an ordered dict. Ordering logic:

- If `section_order` is provided: iterate the list, emit each section that has pages (skipping any names that aren't present), then append remaining sections alphabetically.
- If `section_order` is `None`: sort all sections alphabetically.

### `format_link_entry(page) -> str`

Formats a single page dict as a Markdown link entry:

- `- [Title](url)` when description is empty
- `- [Title](url): description` when description is present (truncated to 500 chars if needed)

## Interaction with other modules

- Receives output from `src.llm.llm_process_pages` (or the rule-based fallback).
- Called by `api/generate.py`; the return value is sent directly to the client.
