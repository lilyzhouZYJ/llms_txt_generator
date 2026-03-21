from urllib.parse import urlparse, urlunparse


def netloc_from_http_url(url: str) -> str:
    """
    Return the authority (host and optional port, userinfo) from a URL, lowercased.

    Prefer this over string splits on ``/`` so ports, IPv6 hosts, and odd schemes parse
    correctly.
    """
    parsed = urlparse(url)
    return (parsed.netloc or "").lower().strip()


def normalize_http_url(url: str) -> str:
    """
    Lowercase scheme and host, strip query and fragment, normalize path trailing slash.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))
