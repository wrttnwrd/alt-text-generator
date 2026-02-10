#!/usr/bin/env python3
"""
Alt Text Generator
Generates alt text for images in a ScreamingFrog CSV using Claude Vision API.
"""

import argparse
import os
import sys
import time
import csv
from typing import List, Dict, Optional
from dotenv import load_dotenv
import pandas as pd

from csv_handler import CSVHandler
from web_scraper import WebScraper, ForbiddenError
from image_handler import ImageHandler, ImageSizeCategory
from alt_text_generator import AltTextGenerator
from progress_tracker import ProgressTracker


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
    # Exclude images with skip messages or size issues
    exclude_patterns = ['skip', 'too small']
    return not any(pattern in alt_lower for pattern in exclude_patterns)


class SimplifiedCSVWriter:
    """Writes simplified CSV (image URL and alt text) line-by-line as backup."""

    def __init__(self, output_path: str):
        """
        Initialize CSV writer.

        Args:
            output_path: Path to write the simplified CSV
        """
        self.output_path = output_path
        self.file = None
        self.writer = None
        self.written_urls = set()  # Track written URLs to avoid duplicates

    def open(self):
        """Open the CSV file and write headers."""
        self.file = open(self.output_path, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['Image URL', 'ALT Text'])
        self.file.flush()
        print(f"✓ Opened backup CSV: {self.output_path}\n")

    def write_row(self, image_url: str, alt_text: str):
        """
        Write a row immediately (for backup).
        Skips images with skip messages or size issues.

        Args:
            image_url: The image URL
            alt_text: The generated alt text
        """
        if self.writer and image_url not in self.written_urls:
            # Only write if alt text is valid (not a skip message)
            if is_valid_alt_text(alt_text):
                self.writer.writerow([image_url, alt_text])
                self.file.flush()  # Flush immediately to disk
            self.written_urls.add(image_url)

    def close(self):
        """Close the CSV file."""
        if self.file:
            self.file.close()
            print(f"✓ Backup CSV saved: {self.output_path}")

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def extract_base_filename(url: str) -> str:
    """
    Extract base filename from URL, removing size suffixes but keeping -1, -2 suffixes.

    Args:
        url: Image URL

    Returns:
        Base filename without size suffixes

    Example:
        https://example.com/image-2048x1366-1-1024x683.jpg -> image-1.jpg
        https://example.com/image-768x1017.jpg -> image.jpg
        https://example.com/image-1.jpg -> image-1.jpg (different image!)
    """
    import re

    # Get filename from URL
    filename = url.split('/')[-1].split('?')[0]

    # Remove ALL -NUMBERxNUMBER patterns (WordPress size variants)
    # Keep -1, -2 suffixes as they indicate different images
    base_filename = re.sub(r'(-\d+x\d+)+', '', filename)

    return base_filename


def load_instructions(instructions_path: str) -> str:
    """
    Load instructions from markdown file.

    Args:
        instructions_path: Path to instructions markdown file

    Returns:
        Instructions content as string
    """
    if not instructions_path or not os.path.exists(instructions_path):
        return ""

    with open(instructions_path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_simplified_csv(csv_handler: CSVHandler, output_path: str):
    """
    Generate a simplified CSV with only unique image URLs and their ALT text.
    Excludes images with skip messages or size issues.

    Args:
        csv_handler: CSV handler instance
        output_path: Path for the output CSV file
    """
    print(f"\nGenerating simplified CSV: {output_path}")

    # Get all rows with ALT text
    df = csv_handler.df
    df_with_alt = df[df['ALT text'].notna() & (df['ALT text'] != '')]

    # Filter out skipped/excluded images
    df_with_alt = df_with_alt[df_with_alt['ALT text'].apply(is_valid_alt_text)]

    # Create simplified dataframe with unique images
    simplified_df = df_with_alt[['Destination', 'ALT text']].drop_duplicates(subset=['Destination'])
    simplified_df.columns = ['Image URL', 'ALT Text']

    # Sort by image URL for easier reference
    simplified_df = simplified_df.sort_values('Image URL')

    # Save to CSV
    simplified_df.to_csv(output_path, index=False)

    print(f"✓ Saved {len(simplified_df)} unique images to {output_path}")


def generate_filename_csv(csv_handler: CSVHandler, output_path: str):
    """
    Generate a CSV with only image filenames (not full URLs) and their ALT text.
    Excludes images with skip messages or size issues.

    Args:
        csv_handler: CSV handler instance
        output_path: Path for the output CSV file
    """
    print(f"Generating filename-only CSV: {output_path}")

    # Get all rows with ALT text
    df = csv_handler.df
    df_with_alt = df[df['ALT text'].notna() & (df['ALT text'] != '')]

    # Filter out skipped/excluded images
    df_with_alt = df_with_alt[df_with_alt['ALT text'].apply(is_valid_alt_text)]

    # Extract filename from URL
    df_with_alt = df_with_alt.copy()
    df_with_alt['Filename'] = df_with_alt['Destination'].apply(lambda url: url.split('/')[-1].split('?')[0])

    # Create simplified dataframe with unique images
    filename_df = df_with_alt[['Filename', 'ALT text']].drop_duplicates(subset=['Filename'])
    filename_df.columns = ['Image Filename', 'ALT Text']

    # Sort by filename for easier reference
    filename_df = filename_df.sort_values('Image Filename')

    # Save to CSV
    filename_df.to_csv(output_path, index=False)

    print(f"✓ Saved {len(filename_df)} unique images to {output_path}")


def main():
    """Main execution function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate alt text for images using Claude Vision API'
    )
    parser.add_argument(
        'csv_file',
        help='Path to the CSV file containing image data'
    )
    parser.add_argument(
        '--instructions',
        '-i',
        help='Path to the instructions markdown file (optional)',
        default=None
    )
    parser.add_argument(
        '--max-cost',
        '-c',
        type=float,
        help='Maximum cost in USD (optional, script will stop if exceeded)',
        default=None
    )
    parser.add_argument(
        '--scrape-delay',
        '-d',
        type=float,
        help='Delay in seconds between scraping each page (default: 0)',
        default=0
    )
    parser.add_argument(
        '--restart',
        '-r',
        action='store_true',
        help='Clear existing ALT text and start processing from scratch'
    )
    parser.add_argument(
        '--output',
        '-o',
        help='Path for simplified output CSV (image URL and ALT text only)',
        default=None
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    api_key = os.getenv('ANTHROPIC_API_KEY')

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment variables")
        print("Please create a .env file with your API key or set the environment variable")
        sys.exit(1)

    # Verify CSV file exists
    if not os.path.exists(args.csv_file):
        print(f"ERROR: CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Load instructions if provided
    instructions = load_instructions(args.instructions)
    if args.instructions and instructions:
        print(f"✓ Loaded instructions from: {args.instructions}\n")

    # Initialize components
    print("Initializing...")
    csv_handler = CSVHandler(args.csv_file)
    scraper = WebScraper()
    image_handler = ImageHandler()
    alt_generator = AltTextGenerator(api_key, instructions)

    try:
        # Load CSV
        print("Loading CSV...")
        df = csv_handler.load()
        print(f"✓ Loaded {len(df)} total rows from CSV\n")

        # Handle restart flag with confirmation
        if args.restart:
            # Count existing alt text
            existing_alt_text = csv_handler.df['ALT text'].notna() & (csv_handler.df['ALT text'] != '')
            existing_count = existing_alt_text.sum()

            if existing_count > 0:
                print("=" * 60)
                print("⚠️  WARNING: RESTART MODE")
                print("=" * 60)
                print(f"This will DELETE {existing_count} existing ALT text entries!")
                print("This action CANNOT be undone.")
                print("=" * 60)

                # Require explicit confirmation
                response = input("\nType 'DELETE ALL' to confirm (or anything else to cancel): ")

                if response != 'DELETE ALL':
                    print("\n❌ Restart cancelled. Your existing data is safe.")
                    print("Tip: The script automatically resumes from where you left off.")
                    sys.exit(0)

                print("\n🗑️  Clearing existing ALT text...")
                csv_handler.df['ALT text'] = ''
                csv_handler.save()
                print("✓ All ALT text cleared. Starting fresh.\n")
            else:
                print("No existing ALT text found. Proceeding with processing.\n")

        # Get rows to process (skip those with existing alt text)
        rows_to_process = csv_handler.get_rows_to_process()
        num_to_process = len(rows_to_process)

        if num_to_process == 0:
            print("No images to process. All rows already have alt text.")
            return

        print(f"Images to process: {num_to_process}")
        print(f"Images with existing alt text (will skip): {len(df) - num_to_process}\n")

        # Estimate cost
        estimated_cost = AltTextGenerator.estimate_cost(num_to_process)
        print(f"Estimated cost: ${estimated_cost:.4f}")

        if args.max_cost and estimated_cost > args.max_cost:
            print(f"ERROR: Estimated cost (${estimated_cost:.4f}) exceeds max cost (${args.max_cost:.4f})")
            sys.exit(1)

        # Confirm to proceed
        response = input("\nProceed with processing? (y/n): ")
        if response.lower() not in ['y', 'yes']:
            print("Cancelled by user")
            return

        print("\n" + "=" * 60)
        print("STARTING PROCESSING")
        print("=" * 60)
        print()

        # Initialize progress tracker
        progress = ProgressTracker(num_to_process)

        # Initialize simplified CSV writer if requested
        simplified_writer = None
        if args.output:
            simplified_writer = SimplifiedCSVWriter(args.output)
            simplified_writer.open()

        try:
            # Process images
            process_images(
                csv_handler,
                rows_to_process,
                scraper,
                image_handler,
                alt_generator,
                progress,
                args.max_cost,
                args.scrape_delay,
                simplified_writer
            )

            # Display summary
            progress.display_summary()

        finally:
            # Close simplified CSV writer
            if simplified_writer:
                simplified_writer.close()

        # Generate filename-only CSV
        if args.output:
            # Generate filename-only version
            base_name = args.output.rsplit('.', 1)[0]
            filename_output = f"{base_name}-filenames.csv"
            generate_filename_csv(csv_handler, filename_output)

        # Cleanup
        print("\nCleaning up temporary files...")
        image_handler.cleanup()
        print("✓ Done")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        if 'progress' in locals():
            progress.display_interrupt_summary()
        # Save any progress made
        csv_handler.save()
        image_handler.cleanup()
        sys.exit(0)

    except ForbiddenError as e:
        print(f"\n\nERROR: {e}")
        print("Received 403 Forbidden error. Stopping as requested.")
        if 'progress' in locals():
            progress.display_interrupt_summary()
        csv_handler.save()
        image_handler.cleanup()
        sys.exit(1)

    except Exception as e:
        print(f"\n\nERROR: {e}")
        if 'progress' in locals():
            progress.display_interrupt_summary()
        # Save any progress made
        if 'csv_handler' in locals():
            csv_handler.save()
        if 'image_handler' in locals():
            image_handler.cleanup()
        sys.exit(1)


def process_images(
    csv_handler: CSVHandler,
    rows_to_process,
    scraper: WebScraper,
    image_handler: ImageHandler,
    alt_generator: AltTextGenerator,
    progress: ProgressTracker,
    max_cost: float = None,
    scrape_delay: float = 0,
    simplified_writer: Optional[SimplifiedCSVWriter] = None
):
    """
    Process all images in batches.

    Args:
        csv_handler: CSV handler instance
        rows_to_process: DataFrame of rows to process
        scraper: Web scraper instance
        image_handler: Image handler instance
        alt_generator: Alt text generator instance
        progress: Progress tracker instance
        max_cost: Maximum cost limit
        scrape_delay: Delay in seconds between scraping pages
        simplified_writer: Optional writer for simplified backup CSV
    """
    # Get unique pages that need scraping
    unique_pages = csv_handler.get_unique_pages()

    # Scrape all pages first
    print(f"Scraping {len(unique_pages)} pages for context...\n")
    page_data = {}

    for page_num, page_url in enumerate(unique_pages, 1):
        # Get all images for this page
        page_rows = csv_handler.get_images_for_page(page_url)
        image_urls = page_rows['Destination'].tolist()
        indices = page_rows.index.tolist()

        # Check if this page has already been scraped by checking the first row
        # A page is considered scraped if 'title tag' column exists and is not NaN
        # (even if it's empty string - that means we scraped but found no title)
        first_row = page_rows.iloc[0]
        already_scraped = (
            'title tag' in first_row.index and
            pd.notna(first_row['title tag'])
        )

        if already_scraped:
            # Use existing data from CSV
            print(f"[{page_num}/{len(unique_pages)}] Already scraped: {page_url}")
            title = str(first_row.get('title tag', ''))[:60]
            h1 = str(first_row.get('H1 tag', ''))[:60]
            print(f"  ↻ Using existing - Title: {title if title else '(none)'}")
            print(f"  ↻ Using existing - H1: {h1 if h1 else '(none)'}")
            print(f"  ↻ {len(image_urls)} image(s) on this page")

            # Load existing data into page_data structure
            page_data[page_url] = {
                'page_data': {
                    'title': str(first_row.get('title tag', '')),
                    'h1': str(first_row.get('H1 tag', '')),
                    'error': None
                },
                'images': {}
            }

            # Load adjacent text for each image from CSV
            for idx, row in page_rows.iterrows():
                img_url = row['Destination']
                page_data[page_url]['images'][img_url] = {
                    'adjacent_text': str(row.get('adjacent text', '')),
                    'error': None
                }

            print()
            continue

        print(f"[{page_num}/{len(unique_pages)}] Scraping: {page_url}")

        try:
            result = scraper.scrape_page(page_url, image_urls)
            page_data[page_url] = result

            # Display what was found
            page_info = result.get('page_data', {})
            if page_info.get('error'):
                print(f"  ✗ Error: {page_info['error']}")
            else:
                title = page_info.get('title', '')[:60]
                h1 = page_info.get('h1', '')[:60]
                print(f"  ✓ Title: {title if title else '(none)'}")
                print(f"  ✓ H1: {h1 if h1 else '(none)'}")
                print(f"  ✓ Found context for {len(image_urls)} image(s)")

            # Update CSV with page-level data immediately
            for idx in indices:
                csv_handler.update_row(
                    idx,
                    **{
                        'title tag': page_info.get('title', ''),
                        'H1 tag': page_info.get('h1', '')
                    }
                )

            # Save after each page
            csv_handler.save()
            print()

        except ForbiddenError:
            raise

        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ Error: {error_msg}\n")
            # Store error for this page
            page_data[page_url] = {
                'page_data': {'title': '', 'h1': '', 'error': error_msg},
                'images': {img_url: {'adjacent_text': '', 'error': error_msg} for img_url in image_urls}
            }

        # Add delay between page scrapes (except after the last page)
        if scrape_delay > 0 and page_num < len(unique_pages):
            time.sleep(scrape_delay)

    print(f"✓ Completed scraping {len(unique_pages)} pages\n")

    # Check for duplicate images in the dataset
    all_image_urls = rows_to_process['Destination'].tolist()
    unique_image_count = len(set(all_image_urls))
    total_image_count = len(all_image_urls)

    if unique_image_count < total_image_count:
        duplicate_count = total_image_count - unique_image_count
        print(f"Detected {duplicate_count} duplicate image(s)")
        print(f"Will process {unique_image_count} unique images and copy alt text to duplicates\n")

    print("=" * 60)
    print("Processing images with Claude Vision API...")
    print("=" * 60)
    print()

    # Track processed images to avoid duplicates
    processed_images = {}  # {image_url: alt_text}
    processed_base_filenames = {}  # {base_filename: alt_text} for detecting resized versions

    # Process images in batches
    batch = []
    batch_indices = []
    batch_base_filenames = {}  # Track base filenames in current batch to avoid variants in same batch
    pending_variants = []  # Store variants found in same batch for processing after batch completes

    for idx, row in rows_to_process.iterrows():
        source_url = row['Source']
        image_url = row['Destination']

        # Check if this exact image URL has already been processed (duplicate)
        if image_url in processed_images:
            alt_text = processed_images[image_url]
            if alt_text:
                # Copy alt text from previously processed instance
                csv_handler.update_row(idx, **{'ALT text': alt_text})
                progress.update(processed=1, last_index=idx)
                print(f"↻ Duplicate image (copied alt text): {image_url}")
            else:
                # Previous instance failed
                csv_handler.update_row(idx, message="Duplicate of failed image")
                progress.update(failed=1, last_index=idx)
            continue

        # Check if this is a resized version of an already-processed image
        base_filename = extract_base_filename(image_url)
        if base_filename in processed_base_filenames:
            alt_text = processed_base_filenames[base_filename]
            if alt_text:
                # Copy alt text from the base image
                csv_handler.update_row(idx, **{'ALT text': alt_text})
                progress.update(processed=1, last_index=idx)
                processed_images[image_url] = alt_text  # Track this variant too
                print(f"⚏ Image variant (copied alt text): {image_url}")
            else:
                # Base image failed
                csv_handler.update_row(idx, message="Variant of failed image")
                progress.update(failed=1, last_index=idx)
                processed_images[image_url] = None
            continue

        # Check if this is a variant of an image already in the current batch
        if base_filename in batch_base_filenames:
            # Store this variant to process after the batch completes
            pending_variants.append({
                'idx': idx,
                'image_url': image_url,
                'base_filename': base_filename
            })
            print(f"⚏ Image variant in batch (will copy after processing): {image_url}")
            continue

        # Check file size from CSV (if Size (Bytes) column exists)
        MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB

        # Try multiple possible column names for file size
        size_column = None
        for col_name in ['Size (Bytes)', 'Size (bytes)', 'Size', 'File Size', 'size']:
            if col_name in row.index:
                size_column = col_name
                break

        if size_column and pd.notna(row[size_column]):
            try:
                file_size_bytes = float(row[size_column])  # Use float to handle various formats
                if file_size_bytes > MAX_FILE_SIZE_BYTES:
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    csv_handler.update_row(idx, message=f"Image too large: {file_size_mb:.2f}MB (max 5MB)")
                    progress.update(skipped=1, last_index=idx)
                    processed_images[image_url] = None  # Mark as failed
                    print(f"⊘ Skipped (too large): {image_url} ({file_size_mb:.2f}MB)")
                    continue
            except (ValueError, TypeError) as e:
                # If we can't parse size, continue with download check
                pass

        # Get page context
        page_context = page_data.get(source_url, {})
        page_info = page_context.get('page_data', {})
        image_info = page_context.get('images', {}).get(image_url, {})

        # Check for scraping errors
        if page_info.get('error') or image_info.get('error'):
            error_msg = page_info.get('error') or image_info.get('error')
            csv_handler.update_row(idx, message=f"Scraping failed: {error_msg}")
            progress.update(failed=1, last_index=idx)
            processed_images[image_url] = None  # Mark as failed
            continue

        # Download and check image
        local_path, size_category, dimensions = image_handler.download_image(image_url)

        if size_category == ImageSizeCategory.TOO_LARGE:
            # Check if it's a file size issue (dimensions will be 0,0) or dimension issue
            if dimensions == (0, 0):
                csv_handler.update_row(idx, message="Image too large: exceeds 5MB file size limit")
            else:
                csv_handler.update_row(idx, message=f"Image too large: {dimensions[0]}x{dimensions[1]}px (max 8000x8000)")
            progress.update(skipped=1, last_index=idx)
            processed_images[image_url] = None  # Mark as failed
            continue

        if local_path is None:
            csv_handler.update_row(idx, message="Failed to download image")
            progress.update(failed=1, last_index=idx)
            processed_images[image_url] = None  # Mark as failed
            continue

        # Final safety check: verify file size on disk before encoding
        try:
            file_size_on_disk = os.path.getsize(local_path)
            if file_size_on_disk > MAX_FILE_SIZE_BYTES:
                file_size_mb = file_size_on_disk / (1024 * 1024)
                csv_handler.update_row(idx, message=f"Image too large: {file_size_mb:.2f}MB (max 5MB)")
                progress.update(skipped=1, last_index=idx)
                processed_images[image_url] = None
                print(f"⊘ Skipped (file too large): {image_url} ({file_size_mb:.2f}MB)")
                continue
        except OSError:
            pass  # If we can't check file size, continue

        # Get image data
        image_base64 = image_handler.get_image_base64(local_path)
        media_type = image_handler.get_image_media_type(local_path)

        if not image_base64:
            csv_handler.update_row(idx, message="Failed to process image file")
            progress.update(failed=1, last_index=idx)
            processed_images[image_url] = None  # Mark as failed
            continue

        # Update CSV with adjacent text immediately
        adjacent_text = image_info.get('adjacent_text', '')
        csv_handler.update_row(idx, **{'adjacent text': adjacent_text})

        # Add to batch
        batch.append({
            'image_base64': image_base64,
            'media_type': media_type,
            'title': page_info.get('title', ''),
            'h1': page_info.get('h1', ''),
            'adjacent_text': adjacent_text,
            'image_url': image_url,
            'index': idx,
            'size_category': size_category
        })
        batch_indices.append(idx)

        # Track this base filename in the current batch
        batch_base_filenames[base_filename] = image_url

        # Process batch when it reaches size limit or for large images
        should_process = (
            len(batch) >= alt_generator.BATCH_SIZE or
            size_category == ImageSizeCategory.LARGE
        )

        if should_process:
            process_batch(batch, batch_indices, csv_handler, alt_generator, progress, processed_images, processed_base_filenames, simplified_writer)

            # Process any pending variants from this batch
            for variant in pending_variants:
                base_filename = variant['base_filename']
                if base_filename in processed_base_filenames:
                    alt_text = processed_base_filenames[base_filename]
                    if alt_text:
                        csv_handler.update_row(variant['idx'], **{'ALT text': alt_text})
                        progress.update(processed=1, last_index=variant['idx'])
                        processed_images[variant['image_url']] = alt_text
                        print(f"⚏ Image variant (copied alt text): {variant['image_url']}")
                    else:
                        csv_handler.update_row(variant['idx'], message="Variant of failed image")
                        progress.update(failed=1, last_index=variant['idx'])
                        processed_images[variant['image_url']] = None

            # Clear batch tracking
            batch = []
            batch_indices = []
            batch_base_filenames = {}
            pending_variants = []

            # Save progress periodically
            csv_handler.save()
            progress.display()

    # Process remaining batch
    if batch:
        process_batch(batch, batch_indices, csv_handler, alt_generator, progress, processed_images, processed_base_filenames, simplified_writer)

        # Process any remaining pending variants
        for variant in pending_variants:
            base_filename = variant['base_filename']
            if base_filename in processed_base_filenames:
                alt_text = processed_base_filenames[base_filename]
                if alt_text:
                    csv_handler.update_row(variant['idx'], **{'ALT text': alt_text})
                    progress.update(processed=1, last_index=variant['idx'])
                    processed_images[variant['image_url']] = alt_text
                    print(f"⚏ Image variant (copied alt text): {variant['image_url']}")
                else:
                    csv_handler.update_row(variant['idx'], message="Variant of failed image")
                    progress.update(failed=1, last_index=variant['idx'])
                    processed_images[variant['image_url']] = None

        csv_handler.save()

    progress.display()


def process_batch(
    batch: List[Dict],
    indices: List[int],
    csv_handler: CSVHandler,
    alt_generator: AltTextGenerator,
    progress: ProgressTracker,
    processed_images: Dict[str, str],
    processed_base_filenames: Dict[str, str],
    simplified_writer: Optional[SimplifiedCSVWriter] = None
):
    """
    Process a batch of images.

    Args:
        batch: List of image data dictionaries
        indices: List of row indices corresponding to batch
        csv_handler: CSV handler instance
        alt_generator: Alt text generator instance
        progress: Progress tracker instance
        processed_images: Dictionary tracking processed image URLs and their alt text
        processed_base_filenames: Dictionary tracking processed base filenames for detecting variants
        simplified_writer: Optional writer for simplified backup CSV
    """
    try:
        # Generate alt text
        results = alt_generator.generate_batch(batch)

        # Display batch processing header
        print(f"\n--- Batch of {len(batch)} image(s) processed ---")

        # Update CSV with results
        for result in results:
            # Find the corresponding index and image data
            idx = None
            img_data = None
            for i, batch_img in enumerate(batch):
                if batch_img['image_url'] == result['image_url']:
                    idx = indices[i]
                    img_data = batch_img
                    break

            if idx is None or img_data is None:
                continue

            if result.get('error'):
                csv_handler.update_row(idx, message=f"API error: {result['error']}")
                progress.update(failed=1, last_index=idx)
                processed_images[result['image_url']] = None  # Mark as failed
                # Display error
                print(f"\n✗ Image: {result['image_url']}")
                print(f"  Error: {result['error']}")
            elif result.get('alt_text'):
                alt_text = result['alt_text']
                csv_handler.update_row(
                    idx,
                    **{
                        'ALT text': alt_text,
                        'title tag': img_data.get('title', ''),
                        'H1 tag': img_data.get('h1', ''),
                        'adjacent text': img_data.get('adjacent_text', '')
                    }
                )
                progress.update(processed=1, last_index=idx)
                processed_images[result['image_url']] = alt_text  # Store for duplicates

                # Also store base filename for detecting variants
                base_filename = extract_base_filename(result['image_url'])
                processed_base_filenames[base_filename] = alt_text

                # Write to simplified CSV immediately (backup)
                if simplified_writer:
                    simplified_writer.write_row(result['image_url'], alt_text)

                # Display success with URL and alt text
                print(f"\n✓ Image: {result['image_url']}")
                print(f"  Alt text: {alt_text}")
            else:
                csv_handler.update_row(idx, message="Failed to generate alt text")
                progress.update(failed=1, last_index=idx)
                processed_images[result['image_url']] = None  # Mark as failed
                # Display failure
                print(f"\n✗ Image: {result['image_url']}")
                print(f"  Error: Failed to generate alt text")

        print()

    except Exception as e:
        # Display batch error
        print(f"\n✗ Batch processing error: {str(e)}")
        print(f"  All {len(batch)} images in this batch marked as failed\n")

        # Mark all images in batch as failed
        for i, idx in enumerate(indices):
            csv_handler.update_row(idx, message=f"Batch processing error: {str(e)}")
            progress.update(failed=1, last_index=idx)
            # Mark in processed_images to avoid reprocessing duplicates
            if i < len(batch):
                processed_images[batch[i]['image_url']] = None


if __name__ == '__main__':
    main()
