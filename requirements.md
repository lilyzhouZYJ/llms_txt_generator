# Requirements: Automated llms.txt Generator

## Overview

A web application that accepts a website URL, crawls its pages, extracts structured content, and generates a spec-compliant `llms.txt` file. The user can copy or download the result directly from the browser.

---

## 1. llms.txt Specification Conformance

The generated file must conform to [llmstxt.org](https://llmstxt.org/). Key rules:

- **Required:** H1 heading with the site/project name
- **Optional but expected:**
  - Blockquote with a brief summary of the site
  - One or more descriptive paragraphs
  - H2 sections grouping links by category (e.g., "Docs", "Blog", "API")
  - Each link entry: `[Page Title](url)` optionally followed by `: short description`
- File is valid Markdown
- Saved/served at `<domain>/llms.txt` (the tool generates the content; deployment is user's responsibility)

---

## 2. Functional Requirements

### 2.1 URL Input
- User enters a full URL (e.g., `https://example.com`) into a form field
- Basic client-side validation: must be a non-empty, well-formed URL
- Optional: depth limit or max-pages input to bound crawl scope

### 2.2 Web Crawler
- Start from the submitted URL (the root page)
- Extract all internal links from each visited page (same domain only)
- Respect a configurable max page limit (default: 20–50 pages) to avoid runaway crawls
- For each page, extract:
  - `<title>` tag or `og:title` meta tag → used as link label
  - `<meta name="description">` or `og:description` → used as link description
  - Page URL
  - H1/H2 headings (to infer page category/section)
- Skip non-HTML resources (images, PDFs, etc.)
- Honor `robots.txt` `Disallow` rules (best-effort)
- Handle redirects; skip pages that return non-2xx status
- Reasonable timeout per page (e.g., 10 seconds)

### 2.3 Content Structuring
- Derive the site name from the root page title or domain name
- Derive a site summary from the root page's meta description or first paragraph
- Group pages into H2 sections by heuristic (e.g., URL path segment: `/blog/*` → "Blog", `/docs/*` → "Documentation", everything else → "Pages")
- Sort pages within sections by discovery order or alphabetically

### 2.4 llms.txt Generation
- Assemble the file in this order:
  1. `# <Site Name>`
  2. `> <Site summary>` (blockquote)
  3. One or more H2 sections with markdown link lists
- Output is plain text (Markdown)
- User can:
  - View the output in a read-only text area on the page
  - Copy to clipboard with one click
  - Download as `llms.txt`

### 2.5 Error Handling
- Display a clear error message if:
  - The URL is unreachable
  - The crawl returns zero valid pages
  - The domain blocks the crawler (403/429)
- Allow the user to try again without refreshing

---

## 3. Non-Functional Requirements

| Concern | Requirement |
|---|---|
| Performance | Crawl should complete within 30 seconds for ≤50 pages |
| Concurrency | Pages may be fetched in parallel (e.g., 5 concurrent requests) |
| Security | Crawler runs server-side; never expose raw HTML to the client |
| CORS | API must be callable from the frontend origin |
| Rate limiting | Basic per-IP rate limiting on the crawl endpoint |

---

## 4. Architecture

### Recommended Stack
- **Frontend:** React (or plain HTML/JS) — simple single-page UI
- **Backend:** Node.js (Express) or Python (FastAPI/Flask) — handles crawling and file generation
- **Crawler library:** `cheerio` + `axios` (Node) or `httpx` + `beautifulsoup4` (Python)

### API Contract

`POST /api/generate`

Request body:
```json
{
  "url": "https://example.com",
  "maxPages": 30
}
```

Response (success):
```json
{
  "llmstxt": "# Example\n> A site about...\n\n## Pages\n- [Home](https://example.com): ...\n"
}
```

Response (error):
```json
{
  "error": "Could not reach https://example.com"
}
```

---

## 5. UI/UX Requirements

- Single page with:
  - A centered input field for the URL
  - A "Generate" button
  - A loading indicator while the crawl runs
  - A text area displaying the generated `llms.txt` on success
  - "Copy" and "Download" buttons below the output
  - An error banner on failure
- Minimal, clean design — no distracting UI elements
- Mobile-responsive layout

---

## 6. Deliverables

| Deliverable | Details |
|---|---|
| Deployed app | Live URL on a hosting platform (Vercel, Render, Railway, Fly.io, etc.) |
| GitHub repo | Public repo with all source code |
| README.md | Setup, local development, and deployment instructions |
| Screenshots or demo video | At least 2 screenshots showing input and output, or a short screen recording |

---

## 7. README.md Requirements

Must include:
- Project description (one paragraph)
- Prerequisites (Node/Python version, package manager)
- Local setup steps (`git clone`, `npm install` / `pip install`, environment variables if any, `npm run dev`)
- How to deploy (which platform, what config is needed)
- Brief description of how the crawler works
- Example output snippet

---

## 8. Out of Scope

- User accounts / authentication
- Storing generated files server-side
- Crawling sites that require JavaScript rendering (JS-heavy SPAs may yield partial results — acceptable)
- Generating `llms-full.txt` (the full-content variant) — optional stretch goal
