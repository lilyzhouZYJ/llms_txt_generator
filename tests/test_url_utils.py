from src.url_utils import netloc_from_http_url, normalize_http_url


def test_normalize_http_url_strips_query_and_fragment():
    assert normalize_http_url("https://Example.com/foo?x=1#h") == "https://example.com/foo"


def test_normalize_http_url_root():
    assert normalize_http_url("HTTPS://EXAMPLE.COM/") == "https://example.com/"


def test_normalize_http_url_default_scheme():
    assert normalize_http_url("//example.com/bar/").startswith("https://")


def test_netloc_from_http_url_host_and_port():
    assert netloc_from_http_url("https://Example.com:8443/path") == "example.com:8443"


def test_netloc_from_http_url_empty_when_no_host():
    assert netloc_from_http_url("") == ""
