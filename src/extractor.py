from urllib.parse import urlparse

from bs4 import BeautifulSoup

_BOILERPLATE_TAGS = ["script", "style", "nav", "header", "footer", "aside"]

_SECTION_MAP = {
    "blog": "Blog",
    "posts": "Blog",
    "articles": "Blog",
    "news": "Blog",
    "docs": "Documentation",
    "documentation": "Documentation",
    "guide": "Documentation",
    "guides": "Documentation",
    "reference": "Documentation",
    "api": "API Reference",
    "about": "About",
    "team": "About",
    "company": "About",
}


def _infer_section(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "Overview"
    first_segment = path.split("/")[0].lower()
    return _SECTION_MAP.get(first_segment, first_segment.capitalize())


def _extract_main_text(html: str, max_chars: int = 3000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_BOILERPLATE_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars]


def extract_metadata(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Title: <title> → og:title → last URL path segment
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()
    if not title:
        path = urlparse(url).path.strip("/")
        title = path.split("/")[-1].replace("-", " ").replace("_", " ").capitalize() if path else url

    # Description: meta description → og:description → ""
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "").strip()
    if not description:
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "").strip()

    return {
        "url": url,
        "title": title,
        "description": description,
        "section": _infer_section(url),
        "main_text": _extract_main_text(html),
    }
