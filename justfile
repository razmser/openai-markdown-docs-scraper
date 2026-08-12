# OpenAI Docs Scraper

# Default recipe
default:
    @just --list

# Install dependencies
install:
    pip install -r requirements.txt

# Run the scraper (discovers pages from the site manifests, then fetches markdown)
scrape:
    python scrape_openai_docs.py

# Re-fetch using the cached page list, skipping the discovery requests
scrape-cached:
    python scrape_openai_docs.py --no-discover

# Fetch only pages missing from docs/ (development shortcut)
scrape-missing:
    python scrape_openai_docs.py --no-discover --skip-existing --no-prune

# Clean generated markdown files and the page cache, keeping docs/plans
clean:
    find docs -mindepth 1 -maxdepth 1 ! -name plans -exec rm -rf {} +

# Copy generated docs to openai-markdown-docs repo
export docs_repo="../openai-markdown-docs":
    rm -rf {{docs_repo}}/api-reference
    mkdir -p {{docs_repo}}/api-reference
    rsync -a --exclude='plans/' docs/ {{docs_repo}}/api-reference/
    @echo "Docs exported to {{docs_repo}}/api-reference"
