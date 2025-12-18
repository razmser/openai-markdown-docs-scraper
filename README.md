# OpenAI Docs Scraper

Scrapes OpenAI API documentation and converts it to Markdown format.

## Prerequisites

- Python 3.8+
- [just](https://github.com/casey/just) (optional, for convenience commands)

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Or with just:

```bash
just install
```

## Usage

Run the scraper:

```bash
python scrape_openai_docs.py
# or
just scrape
```

This will:
1. Download HTML pages to `scraped/` (cached for iterative development)
2. Convert to Markdown in `docs/`

## Updating openai-markdown-docs

After scraping, export the docs to the main repository:

```bash
just export
```

This copies the generated `docs/` folder to `../openai-markdown-docs/api-reference/`.

## Commands

| Command | Description |
|---------|-------------|
| `just install` | Install dependencies and Playwright |
| `just scrape` | Run the scraper |
| `just clean-cache` | Remove cached HTML (forces re-download) |
| `just clean-docs` | Remove generated Markdown |
| `just clean` | Remove both cache and docs |
| `just export` | Copy docs to openai-markdown-docs repo |
