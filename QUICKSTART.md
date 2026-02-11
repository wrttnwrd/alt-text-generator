# Quick Start Guide - Streamlit Interface

Get started with the Alt Text Generator web interface in 3 easy steps!

## Prerequisites

- Python 3.8+ installed
- Anthropic API key

## Step 1: Install Dependencies

```bash
pipenv install
```

## Step 2: Set Up API Key

Create a `.env` file in the project root:

```bash
echo "ANTHROPIC_API_KEY=your_api_key_here" > .env
```

Replace `your_api_key_here` with your actual Anthropic API key.

## Step 3: Launch the App

```bash
pipenv run streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

## Using the App

### Option 1: Drag and Drop in Browser

1. Drag your CSV file into the upload area
2. (Optional) Drag a YAML config file with the same name (e.g., `iowa.yaml` for `iowa.csv`)
3. The app automatically queues and processes files
4. Watch real-time progress
5. Download results from the `output/` folder

### Option 2: Drop Files in Watched Folder

1. Place CSV files directly in the `watched/` folder
2. (Optional) Place YAML config files with matching names
3. The app automatically detects and processes them
4. Results appear in the `output/` folder

## Output Files

For a CSV named `iowa.csv`, the app generates:

- `output/iowa-original-updated.csv` - Original CSV with alt text added
- `output/iowa-simplified.csv` - Just image URLs and alt text
- `output/iowa-filenames-only.csv` - Just filenames and alt text

## Configuration (Optional)

Create a YAML file with the same name as your CSV:

**Example: `iowa.yaml`**

```yaml
instructions: |
  Keep alt text between 125-150 characters.
  Focus on wedding scenes and emotions.
  Don't name specific flower types, use "blooms".

max_cost: 5.0          # Stop if estimated cost exceeds $5
scrape_delay: 1.0      # Wait 1 second between page scrapes
restart: false         # Set to true to clear existing alt text
```

## That's It!

The app handles everything automatically:
- ✓ Queue management
- ✓ Processing one file at a time
- ✓ Real-time status updates
- ✓ Error tracking
- ✓ Automatic cleanup of processed files

## Need Help?

- Check the main [README.md](README.md) for detailed documentation
- See [example-config.yaml](example-config.yaml) for configuration options
- Use the CLI for advanced scripting: `python generate_alt_text.py --help`
