"""
Core processing module for alt text generation.

Provides a programmatic interface to the alt text generation workflow,
allowing it to be called by both CLI and Streamlit interfaces.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dotenv import load_dotenv
import pandas as pd

from csv_handler import CSVHandler
from web_scraper import WebScraper, ForbiddenError
from image_handler import ImageHandler, ImageSizeCategory
from alt_text_generator import AltTextGenerator
from progress_tracker import ProgressTracker
from config_handler import ProcessingConfig


def is_valid_alt_text(alt_text: str) -> bool:
    """
    Check if alt text is valid (not a skip/error message).

    Args:
        alt_text: The alt text to check

    Returns:
        True if valid, False if it should be excluded
    """
    if pd.isna(alt_text) or alt_text == '':
        return False

    alt_lower = str(alt_text).lower()
    # Exclude images with skip messages, size issues, or errors
    exclude_patterns = ['skip', 'too small', 'download error', 'error:', 'icon', 'thumbnail', 'avatar']
    return not any(pattern in alt_lower for pattern in exclude_patterns)


def extract_base_filename(url: str) -> str:
    """
    Extract base filename from URL, removing size suffixes but keeping -1, -2 suffixes.

    Examples:
        image-300x300.jpg -> image.jpg
        image-1-300x300.jpg -> image-1.jpg
        image-scaled.jpg -> image.jpg
        image-1.jpg -> image-1.jpg

    Args:
        url: Image URL

    Returns:
        Base filename without size suffixes
    """
    import re

    # Get filename from URL
    filename = url.split('/')[-1].split('?')[0]

    # Remove common WordPress size patterns
    # Pattern: -WIDTHxHEIGHT (e.g., -300x300, -1024x768)
    filename = re.sub(r'-\d+x\d+(\.[a-zA-Z]+)$', r'\1', filename)

    # Pattern: -scaled
    filename = re.sub(r'-scaled(\.[a-zA-Z]+)$', r'\1', filename)

    return filename


class ProcessingResults:
    """Container for processing results."""

    def __init__(self):
        self.total_processed = 0
        self.total_skipped = 0
        self.total_failed = 0
        self.estimated_cost = 0.0
        self.output_files = []
        self.errors = []
        self.skipped_images = []


def process_csv_file(
    csv_path: Path,
    config: ProcessingConfig,
    output_dir: Path,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> ProcessingResults:
    """
    Process a CSV file to generate alt text for images.

    Args:
        csv_path: Path to the CSV file to process
        config: Processing configuration
        output_dir: Directory where output files will be saved
        progress_callback: Optional callback for progress updates.
                          Called with (event_type, data) where event_type is:
                          - 'image_processed': data={'url', 'alt_text', 'status'}
                          - 'image_skipped': data={'url', 'reason'}
                          - 'image_failed': data={'url', 'error'}
                          - 'batch_complete': data={'processed', 'skipped', 'failed'}
        status_callback: Optional callback for status messages (single string)

    Returns:
        ProcessingResults object with statistics and output file paths
    """
    # Load environment variables
    load_dotenv()
    api_key = os.getenv('ANTHROPIC_API_KEY')

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Create output directory if it doesn't exist
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Generate output file paths based on CSV name
    csv_name = csv_path.stem
    original_output = output_dir / f"{csv_name}-original-updated.csv"
    simplified_output = output_dir / f"{csv_name}-simplified.csv"
    filename_output = output_dir / f"{csv_name}-filenames-only.csv"

    results = ProcessingResults()
    results.output_files = [original_output, simplified_output, filename_output]

    # Status callback helper
    def status(msg: str):
        if status_callback:
            status_callback(msg)

    # Initialize components
    status("Initializing...")
    csv_handler = CSVHandler(str(csv_path))
    scraper = WebScraper()
    image_handler = ImageHandler()
    alt_generator = AltTextGenerator(api_key, config.instructions)

    try:
        # Load CSV
        status("Loading CSV...")
        df = csv_handler.load()

        # Handle restart mode
        if config.restart:
            status("Clearing existing alt text...")
            csv_handler.df['ALT text'] = ''
            csv_handler.save()

        # Get rows to process
        rows_to_process = csv_handler.get_rows_to_process()
        num_to_process = len(rows_to_process)

        if num_to_process == 0:
            status("No images to process")
            return results

        # Estimate cost
        estimated_cost = AltTextGenerator.estimate_cost(num_to_process)
        results.estimated_cost = estimated_cost

        # Check max cost
        if config.max_cost and estimated_cost > config.max_cost:
            raise ValueError(f"Estimated cost (${estimated_cost:.4f}) exceeds max cost (${config.max_cost:.4f})")

        status(f"Processing {num_to_process} images (estimated cost: ${estimated_cost:.4f})")

        # Scrape unique pages for context
        unique_pages = csv_handler.get_unique_pages()
        status(f"Scraping {len(unique_pages)} unique pages for context...")

        for i, page_url in enumerate(unique_pages, 1):
            try:
                page_data = scraper.scrape_page(page_url, csv_handler.get_images_for_page(page_url))

                # Update all rows for this page
                for row_idx in df[df['Source'] == page_url].index:
                    image_url = df.at[row_idx, 'Destination']
                    image_data = page_data['images'].get(image_url, {})

                    csv_handler.update_row(row_idx, **{
                        'title tag': page_data['page_data']['title'],
                        'H1 tag': page_data['page_data']['h1'],
                        'adjacent text': image_data.get('adjacent_text', '')
                    })

                csv_handler.save()

                # Apply scrape delay
                if config.scrape_delay and i < len(unique_pages):
                    import time
                    time.sleep(config.scrape_delay)

            except ForbiddenError:
                status(f"403 Forbidden error on {page_url} - stopping")
                raise
            except Exception as e:
                status(f"Error scraping {page_url}: {str(e)}")

        # Initialize progress tracker
        progress = ProgressTracker(num_to_process)

        # Process images
        status("Processing images...")

        # Track processed images
        processed_images = {}  # base_filename -> alt_text
        batch = []
        batch_rows = []

        for idx in rows_to_process.index:
            row = df.loc[idx]
            image_url = row['Destination']
            base_filename = extract_base_filename(image_url)

            # Check if already processed (exact URL)
            if image_url in processed_images:
                alt_text = processed_images[image_url]
                csv_handler.update_row(idx, **{'ALT text': alt_text})
                results.total_skipped += 1
                if progress_callback:
                    progress_callback('image_skipped', {'url': image_url, 'reason': 'duplicate'})
                continue

            # Check if base filename was already processed (variant)
            if base_filename in processed_images:
                alt_text = processed_images[base_filename]
                csv_handler.update_row(idx, **{'ALT text': alt_text})
                processed_images[image_url] = alt_text
                results.total_skipped += 1
                if progress_callback:
                    progress_callback('image_skipped', {'url': image_url, 'reason': 'variant'})
                continue

            # Skip SVG files (icons)
            if image_url.lower().endswith('.svg'):
                skip_msg = "Skipped: SVG icon"
                csv_handler.update_row(idx, **{'ALT text': skip_msg})
                results.total_skipped += 1
                results.skipped_images.append({'url': image_url, 'reason': skip_msg})
                if progress_callback:
                    progress_callback('image_skipped', {'url': image_url, 'reason': skip_msg})
                continue

            # Skip googleusercontent images (avatars)
            if 'googleusercontent' in image_url.lower():
                skip_msg = "Skipped: Avatar (googleusercontent)"
                csv_handler.update_row(idx, **{'ALT text': skip_msg})
                results.total_skipped += 1
                results.skipped_images.append({'url': image_url, 'reason': skip_msg})
                if progress_callback:
                    progress_callback('image_skipped', {'url': image_url, 'reason': skip_msg})
                continue

            # Download and validate image
            try:
                local_path, size_category, dimensions = image_handler.download_image(image_url)

                # Check size category
                if size_category == ImageSizeCategory.TOO_LARGE:
                    error_msg = f"Image too large ({dimensions[0]}x{dimensions[1]} pixels)"
                    csv_handler.update_row(idx, **{'ALT text': error_msg})
                    results.total_skipped += 1
                    results.skipped_images.append({'url': image_url, 'reason': error_msg})
                    if progress_callback:
                        progress_callback('image_skipped', {'url': image_url, 'reason': error_msg})
                    continue

                # Skip small images (likely icons)
                width, height = dimensions
                if width < 100 or height < 100:
                    skip_msg = f"Skipped: Icon/thumbnail ({width}x{height}px, minimum 100x100)"
                    csv_handler.update_row(idx, **{'ALT text': skip_msg})
                    results.total_skipped += 1
                    results.skipped_images.append({'url': image_url, 'reason': skip_msg})
                    if progress_callback:
                        progress_callback('image_skipped', {'url': image_url, 'reason': skip_msg})
                    continue

                # Get image data for API
                image_base64 = image_handler.get_image_base64(local_path)
                media_type = image_handler.get_image_media_type(local_path)

                # Add to batch
                batch.append({
                    'image_url': image_url,
                    'base_filename': base_filename,
                    'local_path': local_path,
                    'image_base64': image_base64,
                    'media_type': media_type,
                    'title': row.get('title tag', ''),
                    'h1': row.get('H1 tag', ''),
                    'adjacent_text': row.get('adjacent text', '')
                })
                batch_rows.append(idx)

                # Process batch when full (or for large images)
                batch_size = 1 if size_category == ImageSizeCategory.LARGE else 8

                if len(batch) >= batch_size:
                    # Process batch
                    try:
                        alt_text_results = alt_generator.generate_batch(batch)

                        for i, result in enumerate(alt_text_results):
                            batch_item = batch[i]
                            row_idx = batch_rows[i]

                            # Extract alt text from result
                            alt_text = result.get('alt_text', '')
                            error = result.get('error')

                            if error:
                                csv_handler.update_row(row_idx, **{'ALT text': f"Error: {error}"})
                                results.total_failed += 1
                                if progress_callback:
                                    progress_callback('image_failed', {
                                        'url': batch_item['image_url'],
                                        'error': error
                                    })
                            else:
                                csv_handler.update_row(row_idx, **{'ALT text': alt_text})
                                processed_images[batch_item['image_url']] = alt_text
                                processed_images[batch_item['base_filename']] = alt_text
                                results.total_processed += 1

                                if progress_callback:
                                    progress_callback('image_processed', {
                                        'url': batch_item['image_url'],
                                        'alt_text': alt_text,
                                        'status': 'success'
                                    })

                        csv_handler.save()

                    except Exception as e:
                        error_msg = f"API error: {str(e)}"
                        for i in range(len(batch)):
                            row_idx = batch_rows[i]
                            csv_handler.update_row(row_idx, **{'ALT text': error_msg})
                            results.total_failed += 1
                            results.errors.append({'url': batch[i]['image_url'], 'error': error_msg})

                            if progress_callback:
                                progress_callback('image_failed', {
                                    'url': batch[i]['image_url'],
                                    'error': error_msg
                                })

                    # Clear batch
                    batch = []
                    batch_rows = []

                    # Update progress
                    progress.update(results.total_processed, results.total_skipped, results.total_failed)

                    if progress_callback:
                        progress_callback('batch_complete', {
                            'processed': results.total_processed,
                            'skipped': results.total_skipped,
                            'failed': results.total_failed
                        })

            except Exception as e:
                error_msg = f"Download error: {str(e)}"
                csv_handler.update_row(idx, **{'ALT text': error_msg})
                results.total_failed += 1
                results.errors.append({'url': image_url, 'error': error_msg})

                if progress_callback:
                    progress_callback('image_failed', {'url': image_url, 'error': error_msg})

        # Process remaining batch
        if batch:
            try:
                alt_text_results = alt_generator.generate_batch(batch)

                for i, result in enumerate(alt_text_results):
                    batch_item = batch[i]
                    row_idx = batch_rows[i]

                    # Extract alt text from result
                    alt_text = result.get('alt_text', '')
                    error = result.get('error')

                    if error:
                        csv_handler.update_row(row_idx, **{'ALT text': f"Error: {error}"})
                        results.total_failed += 1
                        if progress_callback:
                            progress_callback('image_failed', {
                                'url': batch_item['image_url'],
                                'error': error
                            })
                    else:
                        csv_handler.update_row(row_idx, **{'ALT text': alt_text})
                        processed_images[batch_item['image_url']] = alt_text
                        processed_images[batch_item['base_filename']] = alt_text
                        results.total_processed += 1

                        if progress_callback:
                            progress_callback('image_processed', {
                                'url': batch_item['image_url'],
                                'alt_text': alt_text,
                                'status': 'success'
                            })

                csv_handler.save()

            except Exception as e:
                error_msg = f"API error: {str(e)}"
                for i in range(len(batch)):
                    row_idx = batch_rows[i]
                    csv_handler.update_row(row_idx, **{'ALT text': error_msg})
                    results.total_failed += 1
                    results.errors.append({'url': batch[i]['image_url'], 'error': error_msg})

                    if progress_callback:
                        progress_callback('image_failed', {
                            'url': batch[i]['image_url'],
                            'error': error_msg
                        })

        # Save final CSV (original updated)
        csv_handler.df.to_csv(original_output, index=False)

        # Generate simplified CSV (with URLs)
        status("Generating simplified output...")
        simplified_data = []
        for _, row in csv_handler.df.iterrows():
            image_url = row['Destination']
            alt_text = row.get('ALT text', '')

            if is_valid_alt_text(alt_text) and image_url not in [d['Image URL'] for d in simplified_data]:
                simplified_data.append({'Image URL': image_url, 'ALT Text': alt_text})

        simplified_df = pd.DataFrame(simplified_data)
        simplified_df.to_csv(simplified_output, index=False)

        # Generate filename-only CSV
        status("Generating filename-only output...")
        filename_data = []
        for item in simplified_data:
            filename = item['Image URL'].split('/')[-1].split('?')[0]
            filename_data.append({'Image Filename': filename, 'ALT Text': item['ALT Text']})

        filename_df = pd.DataFrame(filename_data)
        filename_df.to_csv(filename_output, index=False)

        # Cleanup
        image_handler.cleanup()

        status("Processing complete!")

    except Exception as e:
        # Cleanup on error
        image_handler.cleanup()
        raise

    return results
