import json
from types import SimpleNamespace

from src.llm import (
    DEFAULT_MODEL,
    ENV_API_KEY,
    _merge_llm_into_pages,
    _rule_based_fallback,
    enrich_pages,
    enrich_with_llm,
)


def _fake_completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_enrich_pages_returns_llm_data_on_success(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Home",
            "description": "Old",
            "section": "Overview",
            "main_text": "Welcome.",
        },
        {
            "url": "https://example.com/blog/a",
            "title": "Post",
            "description": "",
            "section": "Blog",
            "main_text": "Article body.",
        },
    ]
    llm_json = {
        "site_name": "Example Co",
        "site_summary": "A product company.",
        "pages": [
            {
                "url": "https://example.com/",
                "title": "Home",
                "description": "Welcome to our site.",
                "section": "Overview",
            },
            {
                "url": "https://example.com/blog/a",
                "title": "Post",
                "description": "A blog article.",
                "section": "Blog",
            },
        ],
    }
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        return_value=_fake_completion(json.dumps(llm_json))
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, summary = enrich_pages(pages_in, "https://example.com/")

    assert site_name == "Example Co"
    assert summary == "A product company."
    assert out_pages[0]["description"] == "Welcome to our site."
    assert out_pages[0]["section"] == "Overview"
    assert out_pages[1]["section"] == "Blog"
    assert out_pages[1]["description"] == "A blog article."

    call_kw = client.chat.completions.create.call_args.kwargs
    assert call_kw["model"] == DEFAULT_MODEL
    assert call_kw["response_format"] == {"type": "json_object"}


def test_enrich_pages_falls_back_on_api_error(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Root Title",
            "description": "Root desc",
            "section": "Overview",
            "main_text": "",
        },
    ]
    mocker.patch("src.llm._get_openai_client", side_effect=RuntimeError("network"))

    out_pages, site_name, summary = enrich_pages(pages_in, "https://example.com/")

    assert site_name == "Root Title"
    assert summary == "Root desc"
    assert out_pages == pages_in


def test_enrich_pages_falls_back_on_invalid_json(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "T",
            "description": "",
            "section": "Overview",
            "main_text": "",
        },
    ]
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        return_value=_fake_completion("not json {{{")
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, _ = enrich_pages(pages_in, "https://example.com/")

    assert out_pages == pages_in
    assert site_name == "T"


def test_enrich_pages_falls_back_when_site_name_missing(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "T",
            "description": "",
            "section": "Overview",
            "main_text": "",
        },
    ]
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        return_value=_fake_completion(json.dumps({"site_name": "", "pages": []}))
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, _ = enrich_pages(pages_in, "https://example.com/")
    assert out_pages == pages_in
    assert site_name == "T"


def test_enrich_pages_falls_back_without_api_key(mocker):
    mocker.patch.dict("os.environ", {ENV_API_KEY: ""}, clear=False)
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Only",
            "description": "",
            "section": "Overview",
            "main_text": "",
        },
    ]
    out_pages, site_name, _ = enrich_pages(pages_in, "https://example.com/")
    assert out_pages == pages_in
    assert site_name == "Only"


def test_rule_based_fallback_uses_root_page_title():
    pages = [
        {
            "url": "https://example.com/",
            "title": "My Site",
            "description": "Tagline",
            "section": "Overview",
            "main_text": "",
        },
        {
            "url": "https://example.com/x",
            "title": "Other",
            "description": "",
            "section": "X",
            "main_text": "",
        },
    ]
    out, name, summary = _rule_based_fallback(pages, "https://example.com/")
    assert out is pages
    assert name == "My Site"
    assert summary == "Tagline"


def test_rule_based_fallback_uses_domain_when_no_pages():
    out, name, summary = _rule_based_fallback([], "https://example.com/path")
    assert out == []
    assert name == "example.com"
    assert summary == ""


def test_merge_llm_into_pages_preserves_unmatched_urls():
    pages = [
        {
            "url": "https://example.com/a",
            "title": "A",
            "description": "",
            "section": "Overview",
            "main_text": "",
        },
    ]
    data = {"pages": []}
    merged = _merge_llm_into_pages(pages, data)
    assert merged[0]["title"] == "A"


def test_enrich_with_llm_strips_markdown_json_fence(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "H",
            "description": "",
            "section": "Overview",
            "main_text": "x",
        },
    ]
    body = """```json
{"site_name": "S", "site_summary": "", "pages": [{"url": "https://example.com/", "title": "H", "description": "", "section": "Overview"}]}
```"""
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(return_value=_fake_completion(body))
    mocker.patch("src.llm._get_openai_client", return_value=client)

    data = enrich_with_llm(pages_in, "https://example.com/", client=client)
    assert data["site_name"] == "S"
    assert len(data["pages"]) == 1


def test_enrich_pages_empty_list():
    out, name, summary = enrich_pages([], "https://example.com/")
    assert out == []
    assert name == "example.com"
    assert summary == ""
