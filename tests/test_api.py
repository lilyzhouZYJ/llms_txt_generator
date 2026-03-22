"""API tests; crawler and LLM are mocked to avoid real network/API calls."""

import json

import pytest

from api.generate import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_index_redirects_to_static_html(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/index.html"


def test_generate_options_cors_headers(client):
    resp = client.options("/api/generate")
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    assert "POST" in (resp.headers.get("Access-Control-Allow-Methods") or "")
    assert "OPTIONS" in (resp.headers.get("Access-Control-Allow-Methods") or "")


def test_generate_invalid_url(client, mocker):
    mocker.patch("api.generate.crawl")
    mocker.patch("api.generate.llm_process_pages")
    mocker.patch("api.generate.generate_llms_txt")
    resp = client.post(
        "/api/generate",
        data=json.dumps({"url": "ftp://bad"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert json.loads(resp.data)["error"] == "Invalid URL"


async def _empty_crawl(*_args, **_kwargs):
    return []


def test_generate_empty_crawl(client, mocker):
    mocker.patch("api.generate.crawl", side_effect=_empty_crawl)

    resp = client.post(
        "/api/generate",
        data=json.dumps({"url": "https://example.com/"}),
        content_type="application/json",
    )
    assert resp.status_code == 422
    assert "Could not fetch" in json.loads(resp.data)["error"]


async def _fake_crawl(*_args, **_kwargs):
    return [
        {"url": "https://example.com/", "title": "Home", "description": "", "section": "Home"},
    ]


def test_generate_success(client, mocker):
    pages = [
        {"url": "https://example.com/", "title": "Home", "description": "", "section": "Home"},
    ]
    mocker.patch("api.generate.crawl", side_effect=_fake_crawl)
    mocker.patch(
        "api.generate.llm_process_pages",
        return_value=(pages, "Example", "A site.", ["Home"]),
    )
    mocker.patch("api.generate.generate_llms_txt", return_value="# Example\n> A site.\n\n## Home\n- [Home](https://example.com/)\n")

    resp = client.post(
        "/api/generate",
        data=json.dumps({"url": "https://example.com/"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "llmstxt" in data
    assert data["llmstxt"].startswith("# Example")
