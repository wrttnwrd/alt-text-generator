# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python tool that generates alt text for images using the Claude Vision API. It takes a ScreamingFrog crawl CSV (with `Source` page URLs and `Destination` image URLs), scrapes page context (title, H1, adjacent headings/captions), sends images to Claude for analysis, and writes alt text back to the CSV.

## Running the App

### Streamlit web interface (primary)
```bash
pipenv run streamlit run streamlit_app.py
```

### CLI
```bash
pipenv run python generate_alt_text.py path/to/file.csv [OPTIONS]
```
Options: `-i/--instructions PATH`, `-c/--max-cost FLOAT`, `-d/--scrape-delay FLOAT`, `-r/--restart`, `-o/--output PATH`

### Setup
```bash
pipenv install
# Create .env with ANTHROPIC_API_KEY=your_key
```

## Architecture

Two entry points share the same processing pipeline:

- **`generate_alt_text.py`** - CLI entry point with interactive prompts (restart confirmation, cost approval). Contains its own `process_images()` and `process_batch()` functions, plus `SimplifiedCSVWriter` for real-time line-by-line CSV backup.
- **`streamlit_app.py`** - Web UI entry point. Uses `processor.py` (not the CLI's processing logic) with callback-based progress/status reporting.
- **`processor.py`** - Core processing function `process_csv_file()` used by Streamlit. Accepts `progress_callback` and `status_callback` for UI updates. Produces three output files: `{name}-original-updated.csv`, `{name}-simplified.csv`, `{name}-filenames-only.csv`.

Both paths use the same component modules:
- **`csv_handler.py`** - Pandas-based CSV I/O. Required columns: `Source`, `Destination`. Adds: `title tag`, `H1 tag`, `adjacent text`, `message`, `ALT text`.
- **`web_scraper.py`** - Scrapes pages via requests+BeautifulSoup. Extracts title, H1, figcaptions, and preceding H2-H4. Raises `ForbiddenError` on 403 (causes immediate stop).
- **`image_handler.py`** - Downloads images, checks dimensions/file size, converts to base64. Size categories: NORMAL (<2000px), LARGE (2000-8000px, processed individually), TOO_LARGE (>8000px or >5MB, skipped).
- **`alt_text_generator.py`** - Sends batches of up to 8 images to Claude API (`claude-sonnet-4-5-20250929`). Parses "Image N:" response format. Retries with exponential backoff.
- **`config_handler.py`** - Loads per-file YAML config (e.g., `iowa.yaml` for `iowa.csv`). Fields: `instructions`, `max_cost`, `scrape_delay`, `restart`.
- **`processing_queue.py`** / **`file_watcher.py`** - Queue management and watchdog-based directory monitoring for the Streamlit interface. Watches `watched/` directory.

## Key Behaviors

- **Duplicate handling**: Both entry points deduplicate by exact URL and by base filename (strips WordPress `-WIDTHxHEIGHT` suffixes). Alt text is copied to all variants.
- **Auto-skip rules**: SVGs, googleusercontent URLs (avatars), images <100x100px, images >5MB or >8000px.
- **Resume**: Rows with existing `ALT text` are skipped automatically. Progress is saved to CSV after each batch.
- **Streamlit directories**: `watched/` for input files, `output/` for results. Completed input files are deleted from `watched/`.

## Environment

- Python 3, managed with pipenv
- `.env` file holds `ANTHROPIC_API_KEY` (required)
- No test suite exists
