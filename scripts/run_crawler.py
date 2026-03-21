#!/usr/bin/env python3
"""
Validate crawler output on a real website.

Usage:
    python scripts/run_crawler.py https://example.com [max_pages]

Examples:
    python scripts/run_crawler.py https://example.com
    python scripts/run_crawler.py https://example.com 10
"""

import asyncio
import sys

sys.path.insert(0, ".")
from src.crawler import crawl

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print(f"Crawling: {url}  (max_pages={max_pages})\n")

    pages = asyncio.run(crawl(url, max_pages=max_pages))

    if not pages:
        print("ERROR: no pages returned — site may be unreachable or blocking crawlers.")
        sys.exit(1)

    print(f"Found {len(pages)} page(s):\n")
    for i, page in enumerate(pages, 1):
        title = page.get("title") or "(no title)"
        desc  = page.get("description") or "(no description)"
        section = page.get("section", "?")
        text_len = len(page.get("main_text", ""))

        print(f"  [{i:02d}] {page['url']}")
        print(f"        title   : {title}")
        print(f"        desc    : {desc[:100]}{'...' if len(desc) > 100 else ''}")
        print(f"        section : {section}")
        print(f"        text    : {text_len} chars extracted")
        print()

    sections = {}
    for p in pages:
        sections.setdefault(p.get("section", "?"), []).append(p["url"])

    print("Section summary:")
    for section, urls in sorted(sections.items(), key=lambda x: (x[0] != "Overview", x[0])):
        print(f"  {section} ({len(urls)} page{'s' if len(urls) != 1 else ''})")

if __name__ == "__main__":
    main()
