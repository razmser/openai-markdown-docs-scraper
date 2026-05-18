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

## CI Workflow

A GitHub Actions workflow (`.github/workflows/scrape.yml`) runs daily at 06:00 UTC and pushes updated docs to [openai-markdown-docs](https://github.com/razmser/openai-markdown-docs).

The workflow:
1. Checks out this repo and sets up Python 3.12
2. Clones `openai-markdown-docs` using a PAT
3. Copies `.url_cache.json` from the docs repo
4. Runs the scraper with `--no-discover` (uses cached URLs only)
5. Exports docs and commits any changes

### Secret setup

The workflow requires a `DOCS_REPO_TOKEN` repository secret — a fine-grained personal access token with **contents:write** permission on the `openai-markdown-docs` repo.

### Manual cache refresh

The URL cache (`.url_cache.json`) lives in `openai-markdown-docs` at `api-reference/.url_cache.json`. To refresh it manually:

```bash
just scrape        # re-discovers all URLs and updates the cache
just export        # copies docs/ → ../openai-markdown-docs/api-reference/
# then commit .url_cache.json in the docs repo
```
