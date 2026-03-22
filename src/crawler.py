"""
BFS crawler; fetch pages, extract internal links, extract metadata using the extractor module.
"""

import asyncio
import traceback
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.extractor import extract_metadata
from src.url_utils import normalize_http_url

USER_AGENT = "llms-txt-generator/1.0"
TIMEOUT = 10.0
MAX_CONCURRENCY = 10

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
        normalized_url = normalize_http_url(absolute_url)
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
    Crawl from start_url using a semaphore to keep MAX_CONCURRENCY requests
    in flight at all times. Each completed fetch immediately spawns tasks for
    its discovered links rather than waiting for the rest of the batch.
    """
    start_url = normalize_http_url(start_url)
    if not is_allowed_url(start_url, start_url):
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    visited: set[str] = {start_url}
    results: list[dict] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        async def visit(url: str, depth: int) -> None:
            if len(results) >= max_pages:
                return
            async with semaphore:
                html = await fetch_page(client, url)
            if html is None:
                return
            if len(results) >= max_pages:
                return
            results.append(extract_metadata(html, url))
            if depth >= max_crawl_depth:
                return
            child_tasks = []
            for link in get_internal_links(html, url, start_url):
                if link not in visited:
                    visited.add(link)
                    child_tasks.append(asyncio.create_task(visit(link, depth + 1)))
            if child_tasks:
                await asyncio.gather(*child_tasks)

        await visit(start_url, 0)

    return results
