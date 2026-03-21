"""Assemble llms.txt from enriched page dicts; no HTTP, no LLM."""

from __future__ import annotations

DESCRIPTION_MAX_LEN = 500


def group_by_section(pages: list[dict]) -> dict[str, list[dict]]:
    """Group pages by section; Overview first, then alphabetically by section name."""
    groups: dict[str, list[dict]] = {}
    for p in pages:
        sec = p.get("section", "Pages")
        if sec not in groups:
            groups[sec] = []
        groups[sec].append(p)

    overview = [("Overview", groups.pop("Overview"))] if "Overview" in groups else []
    rest = sorted(groups.items())
    return dict(overview + rest)


def format_link_entry(page: dict) -> str:
    """Return `- [Title](url)` or `- [Title](url): description` (description truncated to 120 chars)."""
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
) -> str:
    """Assemble the llms.txt markdown file."""
    lines: list[str] = [f"# {site_name.strip() or 'Untitled'}"]
    if site_summary.strip():
        lines.append("")
        lines.append(f"> {site_summary.strip()}")
    grouped = group_by_section(pages)
    for section, items in grouped.items():
        lines.append("")
        lines.append(f"## {section}")
        for p in items:
            lines.append(format_link_entry(p))
    return "\n".join(lines) + "\n"
