# OpenAI Docs Scraper

# Default recipe
default:
    @just --list

# Install dependencies
install:
    pip install -r requirements.txt

# Run the scraper (discovers URLs via browser, then fetches markdown)
scrape:
    python scrape_openai_docs.py

# Force re-download all pages
scrape-force:
    python scrape_openai_docs.py --force

# Run without browser discovery (uses cached URLs)
scrape-cached:
    python scrape_openai_docs.py --no-discover

# Clean generated markdown files and URL cache
clean:
    rm -rf docs/

# Copy generated docs to openai-markdown-docs repo
export docs_repo="../openai-markdown-docs":
    rm -rf {{docs_repo}}/api-reference
    cp -r docs {{docs_repo}}/api-reference
    @echo "Docs exported to {{docs_repo}}/api-reference"
