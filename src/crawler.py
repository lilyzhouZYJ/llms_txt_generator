import asyncio
import traceback
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from src.extractor import extract_metadata

USER_AGENT = "llms-txt-generator/1.0"
TIMEOUT = 10.0
MAX_CONCURRENCY = 5

async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """
    Fetch a URL and return HTML text, or None on any failure.
    """
    try:
        response = await client.get(url, timeout=TIMEOUT)
        content_type = response.headers.get("content-type", "")
        if not (200 <= response.status_code < 300):
            return None
        if "text/html" not in content_type:
            return None
        return response.text
    except Exception:
        traceback.print_exc()
        return None

def _normalize_link(url: str) -> str:
    """
    Helper function to strip fragment/query from URLs and normalize path.
    e.g. /foo?sort=asc -> /foo
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    # strip trailing slash from path, unless we are at root
    # e.g. /foo/ -> /foo, /foo -> /foo, / -> /
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))

def _is_same_domain(link_netloc: str, base_netloc: str) -> bool:
    """
    True if link is same domain or subdomain of base (e.g. docs.home.com for home.com).
    """
    link = link_netloc.lower()
    base = base_netloc.lower()
    return link == base or link.endswith("." + base)

def get_internal_links(html: str, base_url: str) -> list[str]:
    """
    Get internal links found in an HTML page.
    These are deduplicated and normalized.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc # base domain

    seen: set[str] = set() # deduplication
    links: list[str] = []       # list of output links

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            # check if the href is a valid link
            continue

        # note that if href is an absolute URL, it will be returned as is
        absolute_url = urljoin(base_url, href)

        # check if the link is valid + on the same domain
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if not _is_same_domain(parsed.netloc, base_netloc):
            continue

        normalized_url = _normalize_link(absolute_url)
        if normalized_url not in seen:
            seen.add(normalized_url)
            links.append(normalized_url)

    return links

async def crawl(start_url: str, max_pages: int = 30) -> list[dict]:
    """
    BFS crawl from start_url. Returns a list of page metadata dicts.
    """
    visited: set[str] = set()
    queue: list[str] = [_normalize_link(start_url)]
    results: list[dict] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        while queue and len(results) < max_pages:
            # Pull up to MAX_CONCURRENCY unvisited URLs from the front of the queue
            batch: list[str] = []
            while queue and len(batch) < MAX_CONCURRENCY:
                url = queue.pop(0)
                if url not in visited:
                    visited.add(url)
                    batch.append(url)

            if not batch:
                continue

            htmls = await asyncio.gather(*[fetch_page(client, url) for url in batch])

            for url, html in zip(batch, htmls):
                if html is None:
                    continue
                if len(results) >= max_pages:
                    break

                results.append(extract_metadata(html, url))

                for link in get_internal_links(html, url):
                    # add internal links to the queue
                    if link not in visited:
                        queue.append(link)

    return results
