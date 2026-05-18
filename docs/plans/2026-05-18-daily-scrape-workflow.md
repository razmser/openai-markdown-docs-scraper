# Daily Scrape GitHub Actions Workflow

## Overview
Add a GitHub Actions workflow to the scraper repo that runs daily, fetches fresh markdown docs using cached URLs from the docs repo, exports them to `openai-markdown-docs`, and commits any changes.

## Context
- Files involved: new `.github/workflows/scrape.yml`, `README.md`
- Related patterns: existing `just scrape-cached`, `just export` commands
- Dependencies: Python 3.12 + `requests`, fine-grained PAT stored as `DOCS_REPO_TOKEN` secret
- The `.url_cache.json` lives in `openai-markdown-docs` at `api-reference/.url_cache.json`
- Cache is manually refreshed by running `just scrape` locally, then `just export`, then committing

## Development Approach
- **Testing approach**: Manual (verify via `workflow_dispatch`)
- No application code tests needed — this is a CI workflow

## Implementation Steps

### Task 1: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/scrape.yml`

- [x] Create `.github/workflows/` directory
- [x] Write workflow with `schedule` (daily cron at 06:00 UTC) and `workflow_dispatch` triggers
- [x] Job steps:
  1. Checkout scraper repo
  2. Setup Python 3.12 + `pip install requests`
  3. Clone `openai-markdown-docs` via PAT (`DOCS_REPO_TOKEN` secret)
  4. Copy `.url_cache.json` from docs repo (`api-reference/.url_cache.json`) into scraper `docs/` directory
  5. Run `python scrape_openai_docs.py --no-discover`
  6. Run `just export` (copies `docs/` → docs repo `api-reference/`)
  7. Check for diff in docs repo → if changed, commit with `docs: update YYYY-MM-DD` and push

### Task 2: Verify and document

**Files:**
- Modify: `README.md`

- [ ] Add CI workflow section explaining the daily job
- [ ] Document `DOCS_REPO_TOKEN` secret setup (fine-grained PAT with `contents:write` on `openai-markdown-docs`)
- [ ] Document manual cache refresh workflow: `just scrape` → `just export` → commit `.url_cache.json` to docs repo
- [ ] Trigger workflow manually via `workflow_dispatch` to verify it works
