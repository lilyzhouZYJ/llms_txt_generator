"""Vercel serverless handler: POST /api/generate → crawl, enrich, format llms.txt."""

import asyncio
import re

from flask import Flask, jsonify, redirect, request

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.crawler import crawl
from src.formatter import generate_llms_txt
from src.llm import llm_process_pages

app = Flask(__name__)

URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
DEFAULT_MAX_PAGES = 30

def _after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

app.after_request(_after_request)

@app.route("/")
def index():
    """Vercel runs Flask as one function for all paths; static index lives on the CDN at /index.html."""
    return redirect("/index.html", code=302)

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
        enriched, site_name, site_summary, section_order = llm_process_pages(pages, url)
        llmstxt = generate_llms_txt(
            enriched, site_name, site_summary, section_order=section_order
        )
    except Exception:
        return jsonify(error="Internal server error"), 500

    return jsonify(llmstxt=llmstxt), 200
