# OpenAI Docs Scraper

# Default recipe
default:
    @just --list

# Install dependencies
install:
    pip install -r requirements.txt
    playwright install chromium

# Run the scraper (downloads and converts all pages)
scrape:
    python scrape_openai_docs.py

# Clean cached HTML files (forces re-download on next scrape)
clean-cache:
    rm -rf scraped/

# Clean generated markdown files
clean-docs:
    rm -rf docs/

# Clean everything
clean: clean-cache clean-docs

# Copy generated docs to openai-markdown-docs repo (adjust path as needed)
export docs_repo="../openai-markdown-docs":
    rm -rf {{docs_repo}}/api-reference
    cp -r docs {{docs_repo}}/api-reference
    @echo "Docs exported to {{docs_repo}}/api-reference"
