import httpx
import pytest
import respx

from src.crawler import crawl, fetch_page, get_internal_links, is_allowed_url
from tests.conftest import make_html

# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

BASE_URL = "https://example.com"
HTML_200 = make_html("Home", "A site", ["/about"])


@respx.mock
async def test_fetch_page_returns_html_on_200():
    respx.get(BASE_URL).mock(
        return_value=httpx.Response(200, text=HTML_200, headers={"content-type": "text/html"})
    )
    async with httpx.AsyncClient() as client:
        result = await fetch_page(client, BASE_URL)
    assert result is not None
    assert "Home" in result


@respx.mock
async def test_fetch_page_returns_none_on_404():
    respx.get(BASE_URL).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as client:
        result = await fetch_page(client, BASE_URL)
    assert result is None


@respx.mock
async def test_fetch_page_returns_none_for_non_html_content_type():
    respx.get(BASE_URL).mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
    )
    async with httpx.AsyncClient() as client:
        result = await fetch_page(client, BASE_URL)
    assert result is None


@respx.mock
async def test_fetch_page_returns_none_on_timeout():
    respx.get(BASE_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    async with httpx.AsyncClient() as client:
        result = await fetch_page(client, BASE_URL)
    assert result is None


@respx.mock
async def test_fetch_page_returns_none_on_connect_error():
    respx.get(BASE_URL).mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        result = await fetch_page(client, BASE_URL)
    assert result is None


# ---------------------------------------------------------------------------
# is_allowed_url
# ---------------------------------------------------------------------------


def test_is_allowed_url_root_and_shallow_paths():
    start = "https://example.com/"
    assert is_allowed_url("https://example.com/", start) is True
    assert is_allowed_url("https://example.com/docs", start) is True
    assert is_allowed_url("https://example.com/blogs/post-name", start) is True


def test_is_allowed_url_allows_deep_paths_url_structure_not_limited_here():
    start = "https://example.com/"
    assert is_allowed_url("https://example.com/one/two/three", start) is True


def test_is_allowed_url_rejects_excluded_segments():
    start = "https://example.com/"
    assert is_allowed_url("https://example.com/login", start) is False
    assert is_allowed_url("https://example.com/en/login", start) is False
    assert is_allowed_url("https://example.com/auth/callback", start) is False
    assert is_allowed_url("https://example.com/cdn-cgi/l/email-protection", start) is False
    assert is_allowed_url("https://example.com/_next/static/chunk", start) is False
    assert is_allowed_url("https://example.com/static/app.js", start) is False


def test_is_allowed_url_allows_subdomains():
    start = "https://example.com/"
    assert is_allowed_url("https://docs.example.com/guide", start) is True
    assert is_allowed_url("https://evil.com/", start) is False


# ---------------------------------------------------------------------------
# get_internal_links
# ---------------------------------------------------------------------------


def test_get_internal_links_resolves_relative_urls():
    html = make_html(links=["/about", "/blog/post-1"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert "https://example.com/about" in links
    assert "https://example.com/blog/post-1" in links


def test_get_internal_links_excludes_external_links():
    html = make_html(links=["https://other.com/page", "/internal"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert "https://other.com/page" not in links
    assert "https://example.com/internal" in links


def test_get_internal_links_includes_subdomains():
    html = make_html(links=["https://docs.example.com/guide", "https://blog.example.com/post"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert "https://docs.example.com/guide" in links
    assert "https://blog.example.com/post" in links


def test_get_internal_links_excludes_parent_domain_sibling():
    html = make_html(links=["https://evil-example.com/phishing"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert "https://evil-example.com/phishing" not in links


def test_get_internal_links_deduplicates():
    html = make_html(links=["/about", "/about", "/about#section"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert links.count("https://example.com/about") == 1


def test_get_internal_links_normalizes_root_trailing_slash():
    html = make_html(links=["/", "https://example.com/", "/"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert links.count("https://example.com/") == 1


def test_get_internal_links_strips_query_strings():
    html = make_html(links=["/page?ref=nav", "/page?ref=footer"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert links.count("https://example.com/page") == 1


def test_get_internal_links_skips_non_http_schemes():
    html = make_html(links=["mailto:hello@example.com", "tel:+1234", "javascript:void(0)", "#anchor"])
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert links == []


def test_get_internal_links_returns_empty_for_no_anchors():
    html = make_html()  # no links
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert links == []


def test_get_internal_links_filters_blocked_segments_only():
    html = make_html(
        links=[
            "/login",
            "/signup",
            "/one/two/three",
            "/docs",
            "/blogs/post-slug",
        ]
    )
    links = get_internal_links(html, BASE_URL, BASE_URL)
    assert "https://example.com/login" not in links
    assert "https://example.com/signup" not in links
    assert "https://example.com/one/two/three" in links
    assert "https://example.com/docs" in links
    assert "https://example.com/blogs/post-slug" in links


# ---------------------------------------------------------------------------
# crawl
# ---------------------------------------------------------------------------

HOME_HTML = make_html("Home", "Welcome", ["/about", "/blog"])
ABOUT_HTML = make_html("About", "About us", ["/"])
BLOG_HTML = make_html("Blog", "Our blog", ["/"])

HOP1_HTML = make_html("Hop1", "L1", ["/hop1/hop2"])
HOP2_HTML = make_html("Hop2", "L2", ["/"])


@respx.mock
async def test_crawl_respects_bfs_depth_not_path_segments():
    """max_crawl_depth=1: start (0) + one hop (1); no third level even if URL has many segments."""
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=make_html("Home", "x", ["/hop1"]), headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/hop1").mock(
        return_value=httpx.Response(200, text=HOP1_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/hop1/hop2").mock(
        return_value=httpx.Response(200, text=HOP2_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=10, max_crawl_depth=1)
    urls = [p["url"] for p in results]
    assert "https://example.com/" in urls
    assert "https://example.com/hop1" in urls
    assert "https://example.com/hop1/hop2" not in urls


@respx.mock
async def test_crawl_bfs_depth_two_follows_two_hops():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=make_html("Home", "x", ["/hop1"]), headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/hop1").mock(
        return_value=httpx.Response(200, text=HOP1_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/hop1/hop2").mock(
        return_value=httpx.Response(200, text=HOP2_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=10, max_crawl_depth=2)
    urls = [p["url"] for p in results]
    assert "https://example.com/hop1/hop2" in urls


@respx.mock
async def test_crawl_returns_metadata_for_reachable_pages():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=HOME_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, text=ABOUT_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/blog").mock(
        return_value=httpx.Response(200, text=BLOG_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=10)
    urls = [p["url"] for p in results]

    assert "https://example.com/" in urls
    assert "https://example.com/about" in urls
    assert "https://example.com/blog" in urls


@respx.mock
async def test_crawl_respects_max_pages():
    # Site has 3 pages but we cap at 2
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=HOME_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, text=ABOUT_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/blog").mock(
        return_value=httpx.Response(200, text=BLOG_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=2)
    assert len(results) <= 2


@respx.mock
async def test_crawl_does_not_revisit_urls():
    # Home links to /about; /about links back to /. Home should only appear once.
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=HOME_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, text=ABOUT_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/blog").mock(
        return_value=httpx.Response(200, text=BLOG_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=10)
    urls = [p["url"] for p in results]
    assert urls.count("https://example.com/") == 1


@respx.mock
async def test_crawl_returns_empty_list_when_start_url_unreachable():
    respx.get("https://example.com/").mock(side_effect=httpx.ConnectError("refused"))
    results = await crawl("https://example.com/", max_pages=10)
    assert results == []


@respx.mock
async def test_crawl_skips_non_200_pages():
    # Home is reachable; /about returns 403; /blog returns 200
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text=HOME_HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    respx.get("https://example.com/blog").mock(
        return_value=httpx.Response(200, text=BLOG_HTML, headers={"content-type": "text/html"})
    )

    results = await crawl("https://example.com/", max_pages=10)
    urls = [p["url"] for p in results]
    assert "https://example.com/about" not in urls
    assert "https://example.com/blog" in urls
