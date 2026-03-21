import pytest

from src.extractor import _infer_section, _extract_main_text, extract_metadata


# ---------------------------------------------------------------------------
# _infer_section
# ---------------------------------------------------------------------------

def test_section_inference_root():
    assert _infer_section("https://example.com/") == "Overview"

def test_section_inference_root_no_trailing_slash():
    assert _infer_section("https://example.com") == "Overview"

def test_section_inference_blog():
    assert _infer_section("https://example.com/blog/my-post") == "Blog"

def test_section_inference_posts():
    assert _infer_section("https://example.com/posts/123") == "Blog"

def test_section_inference_docs():
    assert _infer_section("https://example.com/docs/getting-started") == "Documentation"

def test_section_inference_guide():
    assert _infer_section("https://example.com/guide/setup") == "Documentation"

def test_section_inference_api():
    assert _infer_section("https://example.com/api/v2/users") == "API Reference"

def test_section_inference_about():
    assert _infer_section("https://example.com/about") == "About"

def test_section_inference_unknown_segment_capitalizes():
    assert _infer_section("https://example.com/pricing/plans") == "Pricing"


# ---------------------------------------------------------------------------
# _extract_main_text
# ---------------------------------------------------------------------------

def test_main_text_strips_nav_and_footer():
    html = """<html><body>
        <nav>Navigation stuff</nav>
        <header>Header stuff</header>
        <main><p>Real content here.</p></main>
        <footer>Footer stuff</footer>
    </body></html>"""
    text = _extract_main_text(html)
    assert "Real content here." in text
    assert "Navigation stuff" not in text
    assert "Footer stuff" not in text
    assert "Header stuff" not in text

def test_main_text_strips_script_and_style():
    html = """<html><body>
        <script>var x = 1;</script>
        <style>.foo { color: red; }</style>
        <p>Visible text.</p>
    </body></html>"""
    text = _extract_main_text(html)
    assert "Visible text." in text
    assert "var x" not in text
    assert "color: red" not in text

def test_main_text_truncates_to_max_chars():
    long_content = "word " * 1000  # ~5000 chars
    html = f"<html><body><p>{long_content}</p></body></html>"
    text = _extract_main_text(html, max_chars=100)
    assert len(text) <= 100

def test_main_text_returns_empty_for_empty_body():
    html = "<html><body></body></html>"
    text = _extract_main_text(html)
    assert text == ""


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------

def test_extracts_title_from_title_tag():
    html = "<html><head><title>My Page</title></head><body></body></html>"
    meta = extract_metadata(html, "https://example.com/")
    assert meta["title"] == "My Page"


def test_uses_first_title_when_multiple_in_head():
    html = """<html><head>
        <title>Correct</title>
        <title>Ignored duplicate</title>
    </head><body></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["title"] == "Correct"


def test_ignores_svg_title_for_page_title():
    """SVG <title> labels logos; the real document title stays in <head>."""
    html = """<html><head><title>Free AEO Report — See Your Brand</title></head><body>
        <svg xmlns="http://www.w3.org/2000/svg"><title>ChatGPT</title><path d="M0 0"/></svg>
    </body></html>"""
    meta = extract_metadata(html, "https://example.com/aeo-report")
    assert meta["title"] == "Free AEO Report — See Your Brand"


def test_only_svg_titles_fall_back_to_og_title():
    html = """<html><head>
        <meta property="og:title" content="From Open Graph">
    </head><body><svg><title>ChatGPT</title></svg></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["title"] == "From Open Graph"


def test_falls_back_to_og_title():
    html = """<html><head>
        <meta property="og:title" content="OG Title">
    </head><body></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["title"] == "OG Title"

def test_falls_back_to_url_path_when_no_title():
    html = "<html><head></head><body></body></html>"
    meta = extract_metadata(html, "https://example.com/my-page")
    assert meta["title"] == "My page"

def test_extracts_meta_description():
    html = """<html><head>
        <meta name="description" content="A great page.">
    </head><body></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["description"] == "A great page."

def test_falls_back_to_og_description():
    html = """<html><head>
        <meta property="og:description" content="OG description.">
    </head><body></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["description"] == "OG description."

def test_description_empty_when_none_found():
    html = "<html><head><title>Test</title></head><body></body></html>"
    meta = extract_metadata(html, "https://example.com/")
    assert meta["description"] == ""

def test_metadata_includes_correct_url():
    html = "<html><head><title>T</title></head><body></body></html>"
    url = "https://example.com/some/page"
    meta = extract_metadata(html, url)
    assert meta["url"] == url

def test_metadata_includes_section():
    html = "<html><head><title>T</title></head><body></body></html>"
    meta = extract_metadata(html, "https://example.com/blog/post-1")
    assert meta["section"] == "Blog"

def test_metadata_includes_main_text():
    html = "<html><body><p>Hello world.</p></body></html>"
    meta = extract_metadata(html, "https://example.com/")
    assert "Hello world." in meta["main_text"]

def test_title_tag_takes_precedence_over_og_title():
    html = """<html><head>
        <title>Real Title</title>
        <meta property="og:title" content="OG Title">
    </head><body></body></html>"""
    meta = extract_metadata(html, "https://example.com/")
    assert meta["title"] == "Real Title"
