"""Vercel serverless handler: POST /api/generate → crawl, enrich, format llms.txt."""

import asyncio
import re

from flask import Flask, jsonify, request

from src.crawler import crawl
from src.formatter import generate_llms_txt
from src.llm import _normalize_url, enrich_pages

app = Flask(__name__)

URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
DEFAULT_MAX_PAGES = 50

def _after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

app.after_request(_after_request)

@app.route("/api/generate", methods=["POST", "OPTIONS"])
def generate():
    if request.method == "OPTIONS":
        return "", 204
    if request.method != "POST":
        return jsonify(error="Method not allowed"), 405

    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    max_pages = body.get("maxPages", DEFAULT_MAX_PAGES)
    if not isinstance(max_pages, int) or max_pages < 1:
        max_pages = DEFAULT_MAX_PAGES
    max_pages = min(max_pages, 100)

    if not url or not URL_PATTERN.match(url):
        return jsonify(error="Invalid URL"), 400

    try:
        pages = asyncio.run(crawl(url, max_pages=max_pages))
    except Exception:
        return jsonify(error="Internal server error"), 500

    if not pages:
        return (
            jsonify(error=f"Could not fetch any pages from {url}"),
            422,
        )

    try:
        enriched, site_name, site_summary = enrich_pages(pages, url)
        root = _normalize_url(url)
        pages_for_links = [p for p in enriched if _normalize_url(p["url"]) != root]
        llmstxt = generate_llms_txt(pages_for_links, site_name, site_summary)
    except Exception:
        return jsonify(error="Internal server error"), 500

    return jsonify(llmstxt=llmstxt), 200
