from src.formatter import DESCRIPTION_MAX_LEN, format_link_entry, generate_llms_txt, group_by_section


def test_group_by_section_overview_first():
    pages = [
        {"url": "u1", "title": "T", "section": "Blog"},
        {"url": "u2", "title": "T", "section": "Overview"},
        {"url": "u3", "title": "T", "section": "Docs"},
    ]
    grouped = group_by_section(pages)
    keys = list(grouped.keys())
    assert keys[0] == "Overview"
    assert "Blog" in keys
    assert "Docs" in keys


def test_group_by_section_alphabetical_after_overview():
    pages = [
        {"url": "u1", "title": "T", "section": "About"},
        {"url": "u2", "title": "T", "section": "API"},
        {"url": "u3", "title": "T", "section": "Overview"},
    ]
    grouped = group_by_section(pages)
    keys = list(grouped.keys())
    assert keys[0] == "Overview"
    assert keys[1] == "API"
    assert keys[2] == "About"


def test_format_link_entry_no_description():
    page = {"url": "https://x.com/a", "title": "Link"}
    assert format_link_entry(page) == "- [Link](https://x.com/a)"


def test_format_link_entry_with_description():
    page = {"url": "https://x.com/a", "title": "Link", "description": "Short desc"}
    assert format_link_entry(page) == "- [Link](https://x.com/a): Short desc"


def test_format_link_entry_truncates_long_description():
    page = {
        "url": "https://x.com/a",
        "title": "Link",
        "description": "x" * (DESCRIPTION_MAX_LEN + 50),
    }
    out = format_link_entry(page)
    desc = out.split(": ", 1)[-1]
    assert len(desc) == DESCRIPTION_MAX_LEN


def test_generate_llms_txt_has_h1():
    out = generate_llms_txt([], "My Site", "")
    assert out.startswith("# My Site")


def test_generate_llms_txt_has_blockquote_when_summary_present():
    out = generate_llms_txt([], "S", "A summary.")
    assert "> A summary." in out


def test_generate_llms_txt_omits_blockquote_when_summary_empty():
    out = generate_llms_txt([], "S", "")
    assert ">" not in out


def test_generate_llms_txt_has_h2_sections():
    pages = [
        {"url": "u1", "title": "A", "description": "", "section": "Blog"},
        {"url": "u2", "title": "B", "description": "", "section": "Docs"},
    ]
    out = generate_llms_txt(pages, "Site", "Summary")
    assert "## Blog" in out
    assert "## Docs" in out
    assert "- [A](u1)" in out
    assert "- [B](u2)" in out
