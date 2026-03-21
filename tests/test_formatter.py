from src.formatter import DESCRIPTION_MAX_LEN, format_link_entry, generate_llms_txt, group_by_section


def test_group_by_section_sorted_alphabetically():
    pages = [
        {"url": "u1", "title": "T", "section": "Blog"},
        {"url": "u2", "title": "T", "section": "Home"},
        {"url": "u3", "title": "T", "section": "Docs"},
    ]
    grouped = group_by_section(pages)
    keys = list(grouped.keys())
    assert keys == ["Blog", "Docs", "Home"]


def test_group_by_section_alphabetical_all_sections():
    pages = [
        {"url": "u1", "title": "T", "section": "About"},
        {"url": "u2", "title": "T", "section": "API"},
        {"url": "u3", "title": "T", "section": "Zoo"},
    ]
    grouped = group_by_section(pages)
    keys = list(grouped.keys())
    assert keys == ["API", "About", "Zoo"]


def test_group_by_section_respects_section_order():
    pages = [
        {"url": "u1", "title": "T", "section": "Careers"},
        {"url": "u2", "title": "T", "section": "Products"},
    ]
    grouped = group_by_section(pages, section_order=["Products", "Careers"])
    keys = list(grouped.keys())
    assert keys == ["Products", "Careers"]


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
