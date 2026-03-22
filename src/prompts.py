"""System prompts for LLM enrichment (linked summaries → site overview → sections)."""

LINKED_PAGES_SUMMARY_SYSTEM_PROMPT = """You help build an llms.txt file. These pages are **not** the site homepage; H2 sections and the site header are produced in later steps.

You receive JSON for each page: url, title, and main_text (body text, stripped of nav/footer).

Respond with a single JSON object only (no markdown code fences, no commentary):
{
  "pages": [
    { "url": string, "title": string, "description": string }
  ]
}

Rules:
- Output exactly one object per input url (same url strings as provided).
- Fix titles only when main_text shows the provided title is wrong or generic; otherwise prefer the given title.
- **Generate descriptions from main_text** (not meta tags). Neutral, substantive, 1–2 sentences. No CTAs like "Find out how...". Empty description only for minimal pages (login, redirect).
- Do not include site_name or site_summary here.
"""

SITE_OVERVIEW_SYSTEM_PROMPT = """You write the H1 site name and blockquote summary for an llms.txt file.

You receive JSON with:
- base_url: crawl start URL
- homepage: url, title, and main_text (body text) for the **root / homepage**
- linked_pages: other crawled pages, each with url, title, optional crawler **description**, and **main_text** (body excerpt). Use main_text for substance; descriptions may be empty or marketing fluff.

Respond with a single JSON object only (no markdown code fences, no commentary):
{
  "site_name": string,
  "site_summary": string
}

Rules:
- site_name: short, human-readable name for the site (derive mainly from the homepage when possible).
- site_summary: 3–4 sentences for the blockquote under the H1; synthesize the **whole site** using the homepage main_text plus each linked page's main_text (and titles). Neutral and substantive. If there are no linked pages, base site_summary only on the homepage.
- Do not include a pages array; per-page sections are assigned elsewhere.
"""

SECTION_REFINE_SYSTEM_PROMPT = """You assign H2 sections for an llms.txt file. The enrich pass already produced site_name, site_summary, and per-page titles and descriptions.

You receive JSON: site_name, site_summary, crawl start URL, and pages with url, title, optional description, section, and section_hint (path-based hints from the crawler; often identical).

Respond with a single JSON object only (no markdown code fences, no commentary):
{
  "section_order": [ string ],
  "pages": [ { "url": string, "section": string } ]
}

Rules:
- Target **6–8 distinct section names** total. Merge related labels (e.g. "Blog" + "Articles" → one section name).
- If you still have more than 8 section names after merging, **collapse** the extras by assigning those pages to broader existing sections (use site_name and site_summary to judge what fits). You are **renaming and merging buckets**, not deleting pages: **every input url stays in `pages`** with one final `section` string.
- **section_order** lists each distinct section **once**, **most important first** (primary product/docs first; careers, legal, press typically later unless the site is mainly about those).
- Every input url must appear **exactly once** in `pages`—same count as the input list—with its final `section` after all merges.
- Use the same spelling for a section in `section_order` and in each `pages[].section`.
"""
