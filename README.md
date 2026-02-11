# Alt Text Generator

Generate quality, relevant alt text for images found in a ScreamingFrog site crawl using Claude Vision API.

## Features

- **Batch Processing**: Processes multiple images per API call for cost efficiency
- **Duplicate Detection**: Automatically identifies and handles duplicate images, processing each unique image only once
- **Contextual Alt Text**: Uses page title, H1, adjacent headings, and captions to generate relevant alt text
- **Resume Capability**: Automatically skips images that already have alt text
- **Restart Mode**: Option to clear existing alt text and start fresh
- **Dual Output Files**: Generate both full URL and filename-only CSVs (full URLs written line-by-line as backup)
- **Cost Estimation**: Shows estimated API cost before processing
- **Progress Tracking**: Real-time progress display with ETA
- **Error Handling**: Robust error handling with automatic retries
- **Image Size Management**: Handles large images appropriately
- **Custom Instructions**: Support for site-specific instructions via markdown file
- **Rate Limiting**: Configurable delays between page scrapes to avoid 403 errors

## Two Ways to Use

### 1. Streamlit Web Interface (NEW!)

The easiest way to use Alt Text Generator is through the web interface:

1. Start the Streamlit app:
```bash
pipenv run streamlit run streamlit_app.py
```

2. Drag and drop CSV files (and optional YAML config files) into the browser window

3. The app will automatically:
   - Queue files for processing
   - Process them one at a time
   - Show real-time progress and status
   - Display errors and skipped images
   - Show costs after completion
   - Save results to the `output/` folder
   - Clean up processed files from the `watched/` folder

**Features:**
- Drag-and-drop file upload
- Automatic file watching (you can also drop files directly into the `watched/` folder)
- Real-time processing status
- Error and skip logs
- Post-processing statistics (cost, processed, skipped, failed)
- Queue management (processes files one at a time)

**YAML Configuration:**
Place a YAML file with the same name as your CSV (e.g., `iowa.yaml` for `iowa.csv`) to configure processing:

```yaml
# Custom instructions (inline markdown)
instructions: |
  Keep alt text between 125-150 characters.
  Focus on describing the scene and emotions.

# Optional settings
max_cost: 5.0          # Stop if cost exceeds $5
scrape_delay: 1.0      # Wait 1 second between page scrapes
restart: false         # Clear existing alt text
```

See `example-config.yaml` for a complete example.

### 2. Command-Line Interface (Original)

For automation and scripting, use the command-line interface:

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv [OPTIONS]
```

See [CLI Usage](#cli-usage) section below for full details.

## Requirements

- Python 3.8 or higher
- pipenv
- Anthropic API key

## Installation

1. Clone or download this repository

2. Install pipenv if you don't have it:
```bash
pip install pipenv
```

3. Install dependencies:
```bash
pipenv install
```

4. Create a `.env` file in the project root with your Anthropic API key:
```
ANTHROPIC_API_KEY=your_api_key_here
```

## CLI Usage

### Basic Usage

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv
```

Or enter the shell first:
```bash
pipenv shell
python generate_alt_text.py path/to/your/file.csv
```

### With Custom Instructions

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv --instructions files/site-instructions.md
```

### With Cost Limit

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv --max-cost 10.0
```

This will stop the script if the estimated cost exceeds $10.00.

### With Scrape Delay (Rate Limiting)

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv --scrape-delay 2.0
```

This adds a 2-second delay between scraping each page, helping to avoid rate limits or 403 errors.

### Restart Processing (Clear Existing ALT Text)

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv --restart
```

This clears all existing ALT text and starts processing from scratch.

### Generate Output CSV Files

```bash
pipenv run python generate_alt_text.py path/to/your/file.csv --output houston-backup.csv
```

This creates **TWO** output files:
1. `houston-backup.csv` - Full URLs, written line-by-line as backup
2. `houston-backup-filenames.csv` - Just filenames (generated at end)

Perfect for CMS imports or bulk operations!

### Combined Options

```bash
pipenv run python generate_alt_text.py files/data.csv --instructions files/instructions.md --max-cost 20.0 --scrape-delay 1.5 --output alt-text-output.csv --restart
```

## CSV Format

Your input CSV must contain these columns:
- **Source**: The URL of the page containing the image
- **Destination**: The URL of the image itself

The script will automatically add these columns:
- **title tag**: Page title
- **H1 tag**: Page H1 heading
- **adjacent text**: Nearby heading or caption
- **message**: Error or status messages
- **ALT text**: Generated alt text

### Simplified Output CSV (Real-Time Backup)

When using the `--output` flag, **TWO** CSV files are generated:

#### 1. Full URL CSV (Real-Time Backup)
File: `your-output.csv`
- **Image URL**: The complete image URL
- **ALT Text**: The generated alt text
- **Written line-by-line as images are processed** (real-time backup!)
- Survives script interruptions - you never lose your progress

#### 2. Filename-Only CSV (Generated at End)
File: `your-output-filenames.csv`
- **Image Filename**: Just the filename (extracted from URL)
- **ALT Text**: The generated alt text
- Created after processing completes
- Perfect for bulk imports or CMS systems that use filenames

Both CSV files:
- Contains only unique images (duplicates are removed automatically)
- Only includes images with successfully generated alt text
- Sorted alphabetically for easy reference

**Example:**
```bash
--output houston-backup.csv
```
Creates:
- `houston-backup.csv` (full URLs, real-time)
- `houston-backup-filenames.csv` (filenames only, at end)

## Instructions File

Create a markdown file with site-specific instructions for generating alt text. Example:

```markdown
# Instructions for Example Site

- Don't try to name specific flower types. Call them 'blooms'
- Focus on colors and arrangements
- Keep descriptions under 100 characters when possible
- Avoid mentioning brand names
```

## Image Size Handling

The script checks both file size and dimensions to ensure compatibility with Claude Vision:

**File Size Check (Priority):**
- If your CSV has a "Size (Bytes)" column (from ScreamingFrog), the script checks file size BEFORE downloading
- Images > 5MB are skipped immediately: "Image too large: X.XXMBfile (max 5MB)"
- This saves bandwidth and prevents API errors

**Dimension Check:**
- **Normal images** (< 2000x2000 px): Processed in batches of 8
- **Large images** (2000x2000 to 8000x8000 px): Processed individually
- **Too large images** (> 8000x8000 px): Skipped with message "Image too large: [width]x[height]px (max 8000x8000)"

**Fallback:** If no "Size (Bytes)" column exists, the script checks file size after downloading.

## Resume Processing

If the script is interrupted:
1. The CSV is automatically saved with progress
2. Simply run the same command again
3. Images with existing alt text are automatically skipped
4. Processing continues from where it left off

## Error Handling

- **403 Forbidden errors**: Script stops immediately as requested
- **Scraping errors**: Row is skipped with error message
- **API errors**: Automatic retry with exponential backoff
- **Download errors**: Row is skipped with error message

## Cost Estimation

Before processing, the script estimates the API cost based on:
- Number of images to process
- Average image size
- Claude Vision API pricing

Current pricing (claude-sonnet-4-5-20250929):
- Input: $3 per million tokens
- Output: $15 per million tokens
- Images: ~1 token per 0.75KB

## Project Structure

```
alt-text-generator/
├── streamlit_app.py           # Streamlit web interface (NEW!)
├── generate_alt_text.py       # CLI script
├── processor.py               # Core processing logic (NEW!)
├── processing_queue.py        # Queue management (NEW!)
├── file_watcher.py            # Directory monitoring (NEW!)
├── config_handler.py          # YAML config support (NEW!)
├── csv_handler.py             # CSV operations
├── web_scraper.py             # Page scraping
├── image_handler.py           # Image downloading
├── alt_text_generator.py      # Claude API integration
├── progress_tracker.py        # Progress tracking
├── example-config.yaml        # Example YAML configuration (NEW!)
├── Pipfile                    # Python dependencies
├── Pipfile.lock              # Locked dependencies (auto-generated)
├── requirements.txt           # Python dependencies (alternative)
├── .env                       # Environment variables (your API key)
├── .gitignore                # Git ignore rules
├── watched/                  # Drop CSV files here for auto-processing (NEW!)
├── output/                   # Generated output files (NEW!)
└── files/                    # Legacy folder for CLI usage
    ├── your-data.csv
    └── instructions.md
```

## Example Workflow

1. Export image data from ScreamingFrog to CSV
2. Save CSV to the `files/` folder
3. (Optional) Create a site-specific instructions file
4. Enter the pipenv shell:
```bash
pipenv shell
```
5. Run the script:
```bash
python generate_alt_text.py files/your-data.csv --output files/backup.csv --instructions files/site-instructions.md
```
6. Review the estimated cost and confirm
7. Wait for processing to complete
8. Get your results:
   - `files/your-data.csv` - Original file with ALT text added
   - `files/backup.csv` - Full URLs and ALT text (real-time backup)
   - `files/backup-filenames.csv` - Just filenames and ALT text

## Troubleshooting

### API Key Not Found
Ensure your `.env` file exists in the project root and contains:
```
ANTHROPIC_API_KEY=your_actual_api_key
```

### CSV Columns Missing
Verify your CSV has columns named exactly "Source" and "Destination".

### 403 Forbidden Errors
The script stops on 403 errors as requested. This usually means:
- The website is blocking automated requests
- Use the `--scrape-delay` parameter to add delays between page scrapes (e.g., `--scrape-delay 2.0` for 2 seconds)
- Consider starting with a longer delay and reducing it if successful

### High API Costs
- Use the `--max-cost` parameter to set a limit
- Process a small batch first to test
- Consider if you need to process all images

## Advanced Options

### Command Line Arguments

```bash
pipenv run python generate_alt_text.py <csv_file> [OPTIONS]

Arguments:
  csv_file                    Path to the CSV file (required)

Options:
  -i, --instructions PATH     Path to instructions markdown file
  -c, --max-cost FLOAT       Maximum cost in USD
  -d, --scrape-delay FLOAT   Delay in seconds between scraping pages (default: 0)
  -r, --restart              Clear existing ALT text and start from scratch
  -o, --output PATH          Generate simplified CSV with unique images and ALT text
  -h, --help                 Show help message
```

Note: If you're already in a pipenv shell, you can omit `pipenv run` and just use `python generate_alt_text.py`.

## Performance

- Processing speed: ~8 images per API call
- Average time: 2-5 seconds per batch
- Can handle up to 30,000 images (limited by CSV size and time)

## Support

For issues, questions, or contributions, please refer to the project repository.

## License

This project is provided as-is for your use.
