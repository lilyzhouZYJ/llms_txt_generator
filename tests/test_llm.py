import json
import os
from types import SimpleNamespace

import pytest

from src.llm import (
    DEFAULT_MODEL,
    ENV_API_KEY,
    _rule_based_fallback,
    _update_pages_with_llm_sections,
    _update_pages_with_llm_summaries,
    llm_generate_page_summaries,
    llm_generate_site_summary,
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
    linked_json = {
        "pages": [
            {
                "url": "https://example.com/blog/a",
                "title": "Post",
                "description": "A blog article.",
            },
        ],
    }
    site_json = {
        "site_name": "Example Co",
        "site_summary": "A product company.",
    }
    # Homepage is excluded from section refinement — only linked pages are passed
    refine_json = {
        "section_order": ["Writing"],
        "pages": [
            {"url": "https://example.com/blog/a", "section": "Writing"},
        ],
    }
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        side_effect=[
            _fake_completion(json.dumps(linked_json)),
            _fake_completion(json.dumps(site_json)),
            _fake_completion(json.dumps(refine_json)),
        ]
    )
    mocker.patch("src.llm._get_client", return_value=client)

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert site_name == "Example Co"
    assert summary == "A product company."
    # Homepage is excluded; out_pages contains only linked pages
    assert len(out_pages) == 1
    assert out_pages[0]["url"] == "https://example.com/blog/a"
    assert out_pages[0]["description"] == "A blog article."
    assert out_pages[0]["section"] == "Writing"
    assert section_order == ["Writing"]

    assert client.chat.completions.create.call_count == 3
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
    mocker.patch("src.llm._get_client", side_effect=RuntimeError("network"))

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert site_name == "Root Title"
    assert summary == "Root desc"
    assert out_pages == []  # homepage is excluded; no linked pages exist
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
    mocker.patch("src.llm._get_client", return_value=client)

    out_pages, site_name, _, section_order = llm_process_pages(pages_in, "https://example.com/")

    assert out_pages == []  # homepage is excluded; no linked pages exist
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
        return_value=_fake_completion(json.dumps({"site_name": "", "site_summary": ""}))
    )
    mocker.patch("src.llm._get_client", return_value=client)

    out_pages, site_name, _, section_order = llm_process_pages(pages_in, "https://example.com/")
    assert out_pages == []  # homepage is excluded; no linked pages exist
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
    assert out_pages == []  # homepage is excluded; no linked pages exist
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
    merged = _update_pages_with_llm_summaries(pages, [])
    assert merged[0]["title"] == "A"


def test_llm_generate_page_summaries_splits_into_batches(mocker):
    mocker.patch("src.llm.PAGES_PER_LLM_REQUEST", 1)
    linked_pages = [
        {
            "url": "https://example.com/a",
            "title": "A",
            "description": "",
            "section": "X",
            "main_text": "a",
        },
        {
            "url": "https://example.com/b",
            "title": "B",
            "description": "",
            "section": "X",
            "main_text": "b",
        },
    ]
    r1 = {"pages": [{"url": "https://example.com/a", "title": "A", "description": "da"}]}
    r2 = {"pages": [{"url": "https://example.com/b", "title": "B", "description": "db"}]}
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        side_effect=[
            _fake_completion(json.dumps(r1)),
            _fake_completion(json.dumps(r2)),
        ]
    )
    mocker.patch("src.llm._get_client", return_value=client)

    out = llm_generate_page_summaries(linked_pages, "https://example.com/", client=client, parallel=False)

    assert len(out) == 2
    assert out[0]["description"] == "da"
    assert out[1]["description"] == "db"
    assert client.chat.completions.create.call_count == 2
    first_system = client.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "homepage" in first_system.lower()


def test_llm_generate_site_summary_strips_markdown_json_fence(mocker):
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
{"site_name": "S", "site_summary": ""}
```"""
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(return_value=_fake_completion(body))
    mocker.patch("src.llm._get_client", return_value=client)

    site_name, site_summary = llm_generate_site_summary(
        pages_in[0], [], "https://example.com/", client=client
    )
    assert site_name == "S"
    assert site_summary == ""


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
        {
            "url": "https://example.com/about",
            "title": "About",
            "description": "",
            "section": "About",
            "main_text": "About us.",
        },
    ]
    linked_json = {
        "pages": [
            {"url": "https://example.com/about", "title": "About", "description": "About the company."},
        ],
    }
    site_json = {
        "site_name": "Example Co",
        "site_summary": "Summary.",
    }
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.Mock(
        side_effect=[
            _fake_completion(json.dumps(linked_json)),
            _fake_completion(json.dumps(site_json)),
            ValueError("refine failed"),
        ]
    )
    mocker.patch("src.llm._get_client", return_value=client)

    out_pages, site_name, summary, section_order = llm_process_pages(pages_in, "https://example.com/")
    assert site_name == "Example Co"
    assert len(out_pages) == 1
    assert out_pages[0]["url"] == "https://example.com/about"
    assert out_pages[0]["section"] == "About"
    assert section_order is None


def test_update_pages_with_llm_sections_fills_missing_order():
    pages = [
        {
            "url": "https://example.com/a",
            "title": "A",
            "section": "Zebra",
        },
    ]
    data = {
        "section_order": [],
        "pages": [{"url": "https://example.com/a", "section": "Alpha"}],
    }
    merged, order = _update_pages_with_llm_sections(pages, data)
    assert merged[0]["section"] == "Alpha"
    assert order == ["Alpha"]
