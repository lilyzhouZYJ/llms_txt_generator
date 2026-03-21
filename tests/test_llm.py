import json
from types import SimpleNamespace

import pytest

from src.llm import (
    DEFAULT_MODEL,
    ENV_API_KEY,
    _rule_based_fallback,
    _update_pages_with_llm_sections,
    _update_pages_with_llm_summaries,
    llm_generate_page_summaries,
    llm_process_pages,
)


def _fake_completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_llm_process_pages_returns_llm_data_on_success(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Home",
            "description": "Old",
            "section": "Home",
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
            },
            {
                "url": "https://example.com/blog/a",
                "title": "Post",
                "description": "A blog article.",
            },
        ],
    }
    refine_json = {
        "section_order": ["Blog", "Home"],
        "pages": [
            {"url": "https://example.com/", "section": "Home"},
            {"url": "https://example.com/blog/a", "section": "Writing"},
        ],
    }
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        side_effect=[
            _fake_completion(json.dumps(llm_json)),
            _fake_completion(json.dumps(refine_json)),
        ]
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert site_name == "Example Co"
    assert summary == "A product company."
    assert out_pages[0]["description"] == "Welcome to our site."
    assert out_pages[0]["section"] == "Home"
    assert out_pages[1]["section"] == "Writing"
    assert out_pages[1]["description"] == "A blog article."
    assert section_order == ["Home", "Writing"]

    assert client.chat.completions.create.call_count == 2
    call_kw = client.chat.completions.create.call_args.kwargs
    assert call_kw["model"] == DEFAULT_MODEL
    assert call_kw["response_format"] == {"type": "json_object"}


def test_llm_process_pages_falls_back_on_api_error(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Root Title",
            "description": "Root desc",
            "section": "Home",
            "main_text": "",
        },
    ]
    mocker.patch("src.llm._get_openai_client", side_effect=RuntimeError("network"))

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert site_name == "Root Title"
    assert summary == "Root desc"
    assert out_pages == pages_in
    assert section_order is None


def test_llm_process_pages_falls_back_on_invalid_json(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "T",
            "description": "",
            "section": "Home",
            "main_text": "",
        },
    ]
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        return_value=_fake_completion("not json {{{")
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, _, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert out_pages == pages_in
    assert site_name == "T"
    assert section_order is None


def test_llm_process_pages_falls_back_when_site_name_missing(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "T",
            "description": "",
            "section": "Home",
            "main_text": "",
        },
    ]
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        return_value=_fake_completion(json.dumps({"site_name": "", "pages": []}))
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, _, section_order = llm_process_pages(pages_in, "https://example.com/")
    assert out_pages == pages_in
    assert site_name == "T"
    assert section_order is None


def test_llm_process_pages_falls_back_without_api_key(mocker):
    mocker.patch.dict("os.environ", {ENV_API_KEY: ""}, clear=False)
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Only",
            "description": "",
            "section": "Home",
            "main_text": "",
        },
    ]
    out_pages, site_name, _, section_order = llm_process_pages(pages_in, "https://example.com/")
    assert out_pages == pages_in
    assert site_name == "Only"
    assert section_order is None


def test_rule_based_fallback_uses_root_page_title():
    pages = [
        {
            "url": "https://example.com/",
            "title": "My Site",
            "description": "Tagline",
            "section": "Home",
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


def test_rule_based_fallback_empty_pages_uses_netloc_for_site_name():
    out, name, summary = _rule_based_fallback([], "https://example.com/path")
    assert out == []
    assert name == "example.com"
    assert summary == ""


def test_rule_based_fallback_empty_pages_malformed_url_uses_fallback_site_name():
    out, name, summary = _rule_based_fallback([], "")
    assert out == []
    assert name == "Unknown Website"
    assert summary == ""


def test_rule_based_fallback_root_empty_title_uses_fallback_site_name():
    pages = [
        {
            "url": "https://example.com/",
            "title": "",
            "description": "Tagline",
            "section": "Home",
            "main_text": "",
        },
    ]
    out, name, summary = _rule_based_fallback(pages, "https://example.com/")
    assert out is pages
    assert name == "Unknown Website"
    assert summary == "Tagline"


def test_update_pages_with_llm_summaries_preserves_unmatched_urls():
    pages = [
        {
            "url": "https://example.com/a",
            "title": "A",
            "description": "",
            "section": "Other",
            "main_text": "",
        },
    ]
    data = {"pages": []}
    merged = _update_pages_with_llm_summaries(pages, data)
    assert merged[0]["title"] == "A"


def test_llm_generate_page_summaries_strips_markdown_json_fence(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "H",
            "description": "",
            "section": "Home",
            "main_text": "x",
        },
    ]
    body = """```json
{"site_name": "S", "site_summary": "", "pages": [{"url": "https://example.com/", "title": "H", "description": ""}]}
```"""
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(return_value=_fake_completion(body))
    mocker.patch("src.llm._get_openai_client", return_value=client)

    data = llm_generate_page_summaries(pages_in, "https://example.com/", client=client)
    assert data["site_name"] == "S"
    assert len(data["pages"]) == 1
    assert data["pages"][0]["section"] == "Home"


def test_llm_process_pages_empty_raises():
    with pytest.raises(ValueError, match="pages is empty"):
        llm_process_pages([], "https://example.com/")


def test_llm_process_pages_keeps_first_pass_when_refine_fails(mocker):
    pages_in = [
        {
            "url": "https://example.com/",
            "title": "Home",
            "description": "Old",
            "section": "Home",
            "main_text": "Welcome.",
        },
    ]
    llm_json = {
        "site_name": "Example Co",
        "site_summary": "Summary.",
        "pages": [
            {
                "url": "https://example.com/",
                "title": "Home",
                "description": "Welcome to our site.",
            },
        ],
    }
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        side_effect=[
            _fake_completion(json.dumps(llm_json)),
            ValueError("refine failed"),
        ]
    )
    mocker.patch("src.llm._get_openai_client", return_value=client)

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")
    assert site_name == "Example Co"
    assert out_pages[0]["section"] == "Home"
    assert section_order is None


def test_update_pages_with_llm_sections_fills_missing_order():
    pages = [
        {
            "url": "https://example.com/a",
            "title": "A",
            "section": "Zebra",
            "section_hint": "a",
        },
    ]
    data = {
        "section_order": [],
        "pages": [{"url": "https://example.com/a", "section": "Alpha"}],
    }
    merged, order = _update_pages_with_llm_sections(pages, data)
    assert merged[0]["section"] == "Alpha"
    assert order == ["Alpha"]
