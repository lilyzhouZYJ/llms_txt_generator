"""
Data assembly to format the llms.txt file.
"""

# Max length of the description for each link
DESCRIPTION_MAX_LEN = 500

def group_by_section(
    pages: list[dict],
    section_order: list[str] | None = None,
) -> dict[str, list[dict]]:
    """
    Group pages by section.

    If ``section_order`` is set (from the section-refine LLM pass), sections appear in that
    order; any section not listed is appended alphabetically.

    If ``section_order`` is ``None``, sections are sorted alphabetically by name.
    """
    groups: dict[str, list[dict]] = {}
    for p in pages:
        sec = p.get("section", "Pages")
        if sec not in groups:
            groups[sec] = []
        groups[sec].append(p)

    if section_order is None:
        return dict(sorted(groups.items()))

    ordered: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for sec in section_order:
        if sec in groups and sec not in seen:
            ordered[sec] = groups[sec]
            seen.add(sec)
    remaining = sorted(set(groups.keys()) - seen)
    for sec in remaining:
        ordered[sec] = groups[sec]
    return ordered

def format_link_entry(page: dict) -> str:
    """
    Return `- [Title](url)` or `- [Title](url): description` (description truncated to DESCRIPTION_MAX_LEN).
    """
    title = page.get("title", "Untitled").strip()
    url = page.get("url", "")
    desc = (page.get("description") or "").strip()
    base = f"- [{title}]({url})"
    if not desc:
        return base
    if len(desc) > DESCRIPTION_MAX_LEN:
        desc = desc[: DESCRIPTION_MAX_LEN - 3] + "..."
    return f"{base}: {desc}"

def generate_llms_txt(
    pages: list[dict],
    site_name: str,
    site_summary: str,
    section_order: list[str] | None = None,
) -> str:
    """
    Assemble the llms.txt markdown file.

    ``section_order`` controls H2 order when provided (e.g. from the section-refine LLM pass).
    """
    lines: list[str] = [f"# {site_name.strip() or 'Untitled'}"]
    if site_summary.strip():
        lines.append("")
        lines.append(f"> {site_summary.strip()}")
    grouped = group_by_section(pages, section_order=section_order)
    for section, items in grouped.items():
        lines.append("")
        lines.append(f"## {section}")
        for p in items:
            lines.append(format_link_entry(p))
    return "\n".join(lines) + "\n"
