#!/usr/bin/env python3
"""
Validate extractor output on a real URL.

Usage:
    python scripts/run_extractor.py https://example.com/some/page
"""

import sys
import httpx

sys.path.insert(0, ".")
from src.extractor import extract_metadata

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    print(f"Fetching: {url}\n")
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "llms-txt-generator/1.0"})
        response.raise_for_status()
    except Exception as e:
        print(f"ERROR: could not fetch page — {e}")
        sys.exit(1)

    html = response.text
    meta = extract_metadata(html, url)

    print(f"  url         : {meta['url']}")
    print(f"  title       : {meta['title']}")
    print(f"  description : {meta['description'] or '(none)'}")
    print(f"  section     : {meta['section']}")
    print(f"  main_text   : {repr(meta['main_text'][:200])}{'...' if len(meta['main_text']) > 200 else ''}")
    print(f"  text length : {len(meta['main_text'])} chars")

if __name__ == "__main__":
    main()
