"""
BFS crawler; fetch pages, extract internal links, extract metadata using the extractor module.
"""

import asyncio
import traceback
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from src.extractor import extract_metadata

USER_AGENT = "llms-txt-generator/1.0"
TIMEOUT = 10.0
MAX_CONCURRENCY = 5

# Max BFS depth from the start URL (inclusive). Start = 0; first hop = 1; etc.
MAX_CRAWL_DEPTH = 2

# Any path segment in this set rejects the URL (lowercase match).
EXCLUDED_PATH_SEGMENTS = frozenset(
    {
        "login",
        "logout",
        "signin",
        "signup",
        "register",
        "auth",
        "oauth",
        "callback",
        "cdn-cgi",
        "_next",
        "static",
        "assets",
        "admin",
        "wp-admin",
        "wp-login",
        "cart",
        "checkout",
        "account",
        "settings",
        "terms",
        "privacy-policy",
    }
)

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

def is_allowed_url(url: str, start_url: str) -> bool:
    """
    Whether a URL may be fetched: http(s), same domain or subdomain as start_url,
    and no excluded path segments (login, static, _next, etc.).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    # check if the link is on the same domain or a subdomain
    base_netloc = urlparse(start_url).netloc.lower()
    curr_netloc = parsed.netloc.lower()
    if curr_netloc != base_netloc and not curr_netloc.endswith("." + base_netloc):
        return False

    # check if the link is on an excluded path segment
    segments = [s.lower() for s in (parsed.path or "/").strip("/").split("/") if s]
    for seg in segments:
        if seg in EXCLUDED_PATH_SEGMENTS:
            return False

    return True

def get_internal_links(html: str, page_url: str, start_url: str) -> list[str]:
    """
    Get internal links found in an HTML page at page_url.
    These are deduplicated and normalized.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set() # deduplication
    links: list[str] = []       # list of output links

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            # check if the href is a valid link
            continue

        # resolve to absolute URL;
        # note that if href is an absolute URL, it will be returned as is
        absolute_url = urljoin(page_url, href)

        # check if the URL is allowed
        normalized_url = _normalize_link(absolute_url)
        if not is_allowed_url(normalized_url, start_url):
            continue

        # check if the link has been seen before
        if normalized_url not in seen:
            seen.add(normalized_url)
            links.append(normalized_url)

    return links

async def crawl(
    start_url: str,
    max_pages: int = 30,
    max_crawl_depth: int = MAX_CRAWL_DEPTH,
) -> list[dict]:
    """
    BFS crawl from start_url.
    """
    start_url = _normalize_link(start_url)
    if not is_allowed_url(start_url, start_url):
        # sanity check
        return []

    visited: set[str] = {start_url}
    queue: list[tuple[str, int]] = [(start_url, 0)]
    results: list[dict] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        while queue and len(results) < max_pages:
            batch: list[tuple[str, int]] = [] # (url, depth)
            while queue and len(batch) < MAX_CONCURRENCY:
                batch.append(queue.pop(0))

            htmls = await asyncio.gather(*[fetch_page(client, url) for url, _ in batch])

            for (url, depth), html in zip(batch, htmls):
                if html is None:
                    continue
                if len(results) >= max_pages:
                    # we only need to fetch max_pages pages
                    break

                results.append(extract_metadata(html, url))

                next_depth = depth + 1
                if next_depth > max_crawl_depth:
                    # reached max crawl depth
                    continue

                for link in get_internal_links(html, url, start_url):
                    if link not in visited:
                        visited.add(link)
                        queue.append((link, next_depth))

    return results
