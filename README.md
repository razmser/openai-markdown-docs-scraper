# OpenAI Docs Scraper

Scrapes OpenAI API documentation and converts it to Markdown format.

## Prerequisites

- Python 3.8+
- [agent-browser](https://github.com/nichochar/agent-browser) (for URL discovery)
- [just](https://github.com/casey/just) (optional, for convenience commands)

## Setup

```bash
pip install -r requirements.txt
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
1. Use `agent-browser` to discover all API method URLs from the sidebar
2. Fetch raw Markdown from each URL
3. Save files to `docs/`

## Updating openai-markdown-docs

After scraping, export the docs to the main repository:

```bash
just export
```

This copies the generated `docs/` folder to `../openai-markdown-docs/api-reference/`.

## Commands

| Command | Description |
|---------|-------------|
| `just install` | Install Python dependencies |
| `just scrape` | Run the scraper |
| `just scrape-force` | Force re-download all pages |
| `just scrape-cached` | Run with cached URLs (no browser) |
| `just clean` | Remove generated docs and URL cache |
| `just export` | Copy docs to openai-markdown-docs repo |
