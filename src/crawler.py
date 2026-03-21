import asyncio
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from src.extractor import extract_metadata

USER_AGENT = "llms-txt-generator/1.0"
TIMEOUT = 10.0
MAX_CONCURRENCY = 5


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a URL and return HTML text, or None on any failure."""
    try:
        response = await client.get(url, timeout=TIMEOUT)
        content_type = response.headers.get("content-type", "")
        if not (200 <= response.status_code < 300):
            return None
        if "text/html" not in content_type:
            return None
        return response.text
    except Exception:
        return None


def _normalize_link(url: str) -> str:
    """Canonical form: strip fragment/query, normalize path (e.g. / and / are same)."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def get_internal_links(html: str, base_url: str) -> list[str]:
    """Return deduplicated internal links found in html, resolved against base_url."""
    soup = BeautifulSoup(html, "html.parser")
    allowed_netloc = urlparse(base_url).netloc.lower()

    seen: set[str] = set()
    links: list[str] = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.lower() != allowed_netloc:
            continue

        normalized = _normalize_link(absolute)
        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)

    return links


async def crawl(start_url: str, max_pages: int = 30) -> list[dict]:
    """BFS crawl from start_url. Returns a list of page metadata dicts."""
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
                    if link not in visited:
                        queue.append(link)

    return results
