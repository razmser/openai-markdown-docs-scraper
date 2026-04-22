#!/usr/bin/env python3
"""
Scrape OpenAI API docs as individual markdown files from developers.openai.com.

The new site serves raw markdown at URLs like:
  https://developers.openai.com/api/reference/resources/{path}/methods/{method}/index.md

This script:
1. Uses agent-browser to discover all API method URLs from the sidebar navigation
2. Fetches each method's raw markdown via HTTP GET
3. Saves each method as its own .md file in a directory hierarchy
4. Fixes internal links to work with local file structure
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://developers.openai.com"
DOCS_DIR = Path("docs")
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 0.3
MAX_RETRIES = 3
RETRY_BACKOFF = 2


def discover_urls() -> list[dict]:
    """Use agent-browser to extract all API method URLs from the docs sidebar."""
    print("Discovering URLs via agent-browser...")

    js = """
    (() => {
        const links = document.querySelectorAll('nav a[href*="/api/reference/"]');
        const seen = new Set();
        const results = [];
        for (const a of links) {
            const href = a.getAttribute('href');
            const text = a.textContent.trim();
            if (href && !seen.has(href) && !href.includes('#')) {
                seen.add(href);
                results.push({text, href});
            }
        }
        return JSON.stringify(results);
    })()
    """

    result = subprocess.run(
        ["agent-browser", "eval", js],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        print(f"ERROR: agent-browser eval failed: {result.stderr}")
        sys.exit(1)

    raw = result.stdout.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = json.loads(raw)

    links = json.loads(raw)
    print(f"  Found {len(links)} navigation links")

    pages = []
    for link in links:
        href = link["href"]
        text = link["text"]

        if "#" in href:
            continue

        if href.startswith("/api/reference/resources/"):
            pages.append({"text": text, "href": href})
        elif href == "/api/reference/overview":
            pages.append({"text": text, "href": href})

    print(f"  {len(pages)} resource/method links")
    return pages


def href_to_source_url(href: str) -> str:
    """Convert a nav href to the .md source URL."""
    if href == "/api/reference/overview":
        return f"{BASE_URL}{href}.md"
    return f"{BASE_URL}{href}/index.md"


def href_to_local_path(href: str) -> Path:
    """Convert a nav href to a local file path.

    /api/reference/overview
    -> docs/overview.md

    /api/reference/resources/responses/methods/create
    -> docs/responses/create.md

    /api/reference/resources/organization/subresources/admin_api_keys/methods/list
    -> docs/organization/admin_api_keys/list.md

    /api/reference/resources/responses/streaming-events
    -> docs/responses/streaming-events/index.md
    """
    if href == "/api/reference/overview":
        return DOCS_DIR / "overview.md"
    # Strip prefix
    path = href
    for prefix in ["/api/reference/resources/", "/api/reference/"]:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    # Split into parts
    parts = path.split("/")

    # Find the index of "methods" to extract resource path and method name
    if "methods" in parts:
        methods_idx = parts.index("methods")
        resource_parts = parts[:methods_idx]
        method_name = parts[methods_idx + 1] if len(parts) > methods_idx + 1 else "index"

        # Clean resource parts: remove "subresources" markers
        clean = [p for p in resource_parts if p != "subresources"]

        # Build path: resource/.../method.md
        return DOCS_DIR / "/".join(clean) / f"{method_name}.md"
    else:
        # Special pages like streaming-events, client-events, etc.
        clean = [p for p in parts if p != "subresources"]
        return DOCS_DIR / "/".join(clean) / "index.md"


def fetch_markdown(url: str) -> tuple[str | None, int]:
    """Fetch raw markdown with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text, 200
            if resp.status_code in (403, 503) and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** attempt
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after HTTP {resp.status_code}, waiting {wait}s...")
                time.sleep(wait)
                continue
            return None, resp.status_code
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** attempt
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after error: {e}, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"    ERROR: {e}")
            return None, 0
    return None, 0


def build_local_link_map(pages: list[dict]) -> dict[str, str]:
    """Build a map from site href to local relative path for link rewriting."""
    link_map = {}
    for page in pages:
        href = page["href"]
        local = href_to_local_path(href)
        rel = local.relative_to(DOCS_DIR)
        link_map[href] = str(rel.with_suffix("")) if rel.suffix == ".md" else str(rel)
    return link_map


def fix_links(content: str, local_link_map: dict[str, str], source_href: str) -> str:
    """Rewrite links in markdown content.

    - Links to other API methods we've fetched -> local relative paths
    - Other /docs/ links -> absolute developers.openai.com URLs
    - Links to /api/reference/ pages we don't have -> absolute URLs
    """
    # Compute relative path depth for this file
    local_path = href_to_local_path(source_href)
    depth = len(local_path.relative_to(DOCS_DIR).parts) - 1
    prefix = "../" * depth if depth > 0 else ""

    def replace_link(match):
        text = match.group(1)
        url = match.group(2)

        # Already absolute
        if url.startswith("http"):
            return f"[{text}]({url})"

        # Check if it's an API reference link we have locally
        if url in local_link_map:
            return f"[{text}]({prefix}{local_link_map[url]}.md)"

        # Check with stripped trailing slash
        stripped = url.rstrip("/")
        if stripped in local_link_map:
            return f"[{text}]({prefix}{local_link_map[stripped]}.md)"

        # Check partial match (href in url)
        for site_href, local_rel in local_link_map.items():
            if url.endswith(site_href) or site_href.endswith(url.rstrip("/")):
                return f"[{text}]({prefix}{local_rel}.md)"

        # Convert /docs/ links to absolute
        if url.startswith("/docs/"):
            return f"[{text}]({BASE_URL}{url})"

        # Convert /guides/ links to absolute
        if url.startswith("/guides/"):
            return f"[{text}]({BASE_URL}{url})"

        # Convert /api-reference/ links to absolute
        if url.startswith("/api-reference/"):
            return f"[{text}]({BASE_URL}{url})"

        # Leave other relative links as-is
        return match.group(0)

    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, content)
    return content


def main():
    force = "--force" in sys.argv or "-f" in sys.argv
    discover = "--no-discover" not in sys.argv

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("OpenAI API Docs Scraper (developers.openai.com)")
    print(f"Output: {DOCS_DIR}/")
    print(f"Force re-download: {force}")
    print("=" * 60)

    # Step 1: Discover URLs
    if discover:
        pages = discover_urls()
        # Save discovered URLs for caching
        cache_file = DOCS_DIR / ".url_cache.json"
        cache_file.write_text(json.dumps(pages, indent=2))
        print(f"  URL cache saved to {cache_file}")
    else:
        cache_file = DOCS_DIR / ".url_cache.json"
        if not cache_file.exists():
            print("ERROR: No URL cache found. Run without --no-discover first.")
            sys.exit(1)
        pages = json.loads(cache_file.read_text())
        print(f"Loaded {len(pages)} URLs from cache")

    # Step 2: Build link map
    local_link_map = build_local_link_map(pages)

    # Step 3: Fetch all pages
    results = {"success": [], "skipped": [], "failed": []}

    for i, page in enumerate(pages, 1):
        text = page["text"]
        href = page["href"]
        source_url = href_to_source_url(href)
        local_path = href_to_local_path(href)

        print(f"\n[{i}/{len(pages)}] {text}")
        print(f"  URL:   {source_url}")
        print(f"  File:  {local_path}")

        if local_path.exists() and not force:
            size = local_path.stat().st_size
            print(f"  SKIP: exists ({size:,} bytes)")
            results["skipped"].append(href)
            continue

        local_path.parent.mkdir(parents=True, exist_ok=True)

        content, status = fetch_markdown(source_url)

        if content is None or status != 200:
            print(f"  FAIL: HTTP {status}")
            results["failed"].append((href, status))
            continue

        content = fix_links(content, local_link_map, href)

        local_path.write_text(content, encoding="utf-8")
        print(f"  OK: {len(content):,} chars")

        results["success"].append(href)

        if i < len(pages):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Success: {len(results['success'])}")
    print(f"  Skipped: {len(results['skipped'])}")
    print(f"  Failed:  {len(results['failed'])}")

    if results["failed"]:
        print("\n  Failed pages:")
        for href, status in results["failed"]:
            print(f"    - {href} (HTTP {status})")

    print(f"\nDone! {len(results['success'])} files written to {DOCS_DIR}/")
    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
