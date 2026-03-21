def make_html(title: str = "Test Page", description: str = "", links: list[str] | None = None) -> str:
    """Build a minimal HTML page for use in tests."""
    meta = f'<meta name="description" content="{description}">' if description else ""
    anchor_tags = "\n".join(f'<a href="{href}">link</a>' for href in (links or []))
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
  {meta}
</head>
<body>
  {anchor_tags}
</body>
</html>"""
