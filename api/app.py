"""Flask app export for Vercel (`vercel dev` / Flask detection). Logic lives in `generate.py`."""

from .generate import app

__all__ = ["app"]
