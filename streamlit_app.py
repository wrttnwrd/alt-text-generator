"""
Streamlit app for alt text generation with file watching and queue management.

Run with: streamlit run streamlit_app.py
"""

import os
import streamlit as st
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

from processing_queue import ProcessingQueue, ProcessingStatus, ProcessingJob
from config_handler import ProcessingConfig
from processor import process_csv_file
from csv_handler import CSVHandler
from alt_text_generator import AltTextGenerator


# Configuration
WATCHED_DIR = Path("watched")
OUTPUT_DIR = Path("output")


def check_api_key() -> bool:
    """Check if the Anthropic API key is configured."""
    load_dotenv()
    key = os.getenv('ANTHROPIC_API_KEY')
    return bool(key and key.strip() and key != 'your_api_key_here')


def estimate_job_cost(csv_path: Path) -> tuple:
    """
    Estimate cost for a CSV file by counting rows to process.

    Returns:
        Tuple of (num_images, estimated_cost)
    """
    try:
        handler = CSVHandler(str(csv_path))
        df = handler.load()
        rows = handler.get_rows_to_process()
        num_images = len(rows)
        cost = AltTextGenerator.estimate_cost(num_images)
        return num_images, cost
    except Exception:
        return 0, 0.0


def initialize_session_state():
    """Initialize Streamlit session state."""
    if 'queue' not in st.session_state:
        st.session_state.queue = ProcessingQueue(WATCHED_DIR, OUTPUT_DIR)
        # Scan for existing files on startup
        scan_for_new_files()

    if 'current_status' not in st.session_state:
        st.session_state.current_status = ""

    if 'error_log' not in st.session_state:
        st.session_state.error_log = []

    if 'skipped_log' not in st.session_state:
        st.session_state.skipped_log = []

    if 'processing' not in st.session_state:
        st.session_state.processing = False

    if 'confirmed_jobs' not in st.session_state:
        st.session_state.confirmed_jobs = set()


def scan_for_new_files():
    """Scan watched directory for new CSV files and add to queue."""
    new_files = st.session_state.queue.scan_for_new_files()
    for csv_file in new_files:
        st.session_state.queue.add_job(csv_file)


def process_next_job():
    """Process the next job in the queue."""
    queue = st.session_state.queue
    job = queue.get_next_job()

    if not job:
        st.session_state.processing = False
        return

    # Mark as processing
    st.session_state.processing = True
    queue.mark_processing(job)

    # Create placeholders for status updates
    status_container = st.empty()
    progress_container = st.empty()
    progress_text = st.empty()

    # Initialize progress tracking
    if 'progress_total' not in st.session_state:
        st.session_state.progress_total = 0
    if 'progress_current' not in st.session_state:
        st.session_state.progress_current = 0

    try:
        # Load configuration - merge YAML config with sidebar settings
        config = ProcessingConfig.from_csv_path(job.csv_path)

        # Override with sidebar settings if provided
        sidebar_instructions = st.session_state.get('sidebar_instructions', '').strip()
        sidebar_max_cost = st.session_state.get('sidebar_max_cost', 0.0)
        sidebar_scrape_delay = st.session_state.get('sidebar_scrape_delay', 0.0)

        if sidebar_instructions:
            config.instructions = sidebar_instructions
        if sidebar_max_cost > 0:
            config.max_cost = sidebar_max_cost
        if sidebar_scrape_delay > 0:
            config.scrape_delay = sidebar_scrape_delay

        status_container.info(f"Loading configuration for {job.csv_path.name}...")

        # Progress callback
        def on_progress(event_type: str, data: dict):
            if event_type == 'image_processed':
                st.session_state.progress_current += 1
                if st.session_state.progress_total > 0:
                    progress = st.session_state.progress_current / st.session_state.progress_total
                    progress_container.progress(progress)
                    progress_text.text(f"Processing: {st.session_state.progress_current}/{st.session_state.progress_total} images")
            elif event_type == 'image_skipped':
                st.session_state.progress_current += 1
                if st.session_state.progress_total > 0:
                    progress = st.session_state.progress_current / st.session_state.progress_total
                    progress_container.progress(progress)
                    progress_text.text(f"Processing: {st.session_state.progress_current}/{st.session_state.progress_total} images")
                st.session_state.skipped_log.append({
                    'job': job.csv_path.name,
                    'url': data['url'],
                    'reason': data['reason'],
                    'timestamp': datetime.now()
                })
            elif event_type == 'image_failed':
                st.session_state.progress_current += 1
                if st.session_state.progress_total > 0:
                    progress = st.session_state.progress_current / st.session_state.progress_total
                    progress_container.progress(progress)
                    progress_text.text(f"Processing: {st.session_state.progress_current}/{st.session_state.progress_total} images")
                st.session_state.error_log.append({
                    'job': job.csv_path.name,
                    'url': data['url'],
                    'error': data['error'],
                    'timestamp': datetime.now()
                })
            elif event_type == 'batch_complete':
                pass

        # Status callback
        def on_status(msg: str):
            st.session_state.current_status = msg
            status_container.info(f"**{job.csv_path.name}:** {msg}")

            if "Processing" in msg and "images" in msg:
                try:
                    import re
                    match = re.search(r'Processing (\d+) images', msg)
                    if match:
                        st.session_state.progress_total = int(match.group(1))
                        st.session_state.progress_current = 0
                        progress_container.progress(0.0)
                        progress_text.text(f"Processing: 0/{st.session_state.progress_total} images")
                except Exception:
                    pass

        # Process the file
        results = process_csv_file(
            csv_path=job.csv_path,
            config=config,
            output_dir=OUTPUT_DIR,
            progress_callback=on_progress,
            status_callback=on_status
        )

        # Mark as completed
        queue.mark_completed(job, {
            'total_processed': results.total_processed,
            'total_skipped': results.total_skipped,
            'total_failed': results.total_failed,
            'estimated_cost': results.estimated_cost,
            'output_files': results.output_files
        })

        status_container.success(f"Completed: {job.csv_path.name}")
        progress_container.progress(1.0)
        progress_text.text(f"Completed: {st.session_state.progress_total}/{st.session_state.progress_total} images")

    except Exception as e:
        queue.mark_failed(job, str(e))
        st.session_state.error_log.append({
            'job': job.csv_path.name,
            'url': 'N/A',
            'error': str(e),
            'timestamp': datetime.now()
        })
        status_container.error(f"Failed: {job.csv_path.name} - {str(e)}")

    finally:
        queue.cleanup_completed_jobs()
        st.session_state.processing = False


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Alt Text Generator",
        page_icon="🖼️",
        layout="wide"
    )

    # Initialize session state
    initialize_session_state()

    # Only scan for new files if we're not currently processing
    if not st.session_state.processing:
        scan_for_new_files()

    # --- Sidebar: Settings ---
    with st.sidebar:
        st.header("Settings")

        # API key status
        api_key_ok = check_api_key()
        if api_key_ok:
            st.success("API key configured", icon="\u2705")
        else:
            st.error("API key missing or invalid", icon="\u26a0\ufe0f")
            st.caption("Set `ANTHROPIC_API_KEY` in your `.env` file.")

        st.divider()

        # Instructions
        st.subheader("Instructions")
        st.caption("Override YAML config instructions. Leave blank to use YAML or defaults.")
        st.text_area(
            "Custom instructions for alt text generation",
            key='sidebar_instructions',
            height=150,
            placeholder="e.g., Keep alt text under 125 characters.\nFocus on describing people and actions.",
            label_visibility="collapsed"
        )

        st.divider()

        # Processing options
        st.subheader("Processing Options")
        st.number_input(
            "Max cost (USD)",
            min_value=0.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key='sidebar_max_cost',
            help="Stop processing if estimated cost exceeds this. 0 = no limit."
        )
        st.number_input(
            "Scrape delay (seconds)",
            min_value=0.0,
            value=0.0,
            step=0.5,
            format="%.1f",
            key='sidebar_scrape_delay',
            help="Delay between scraping pages to avoid 403 errors. 0 = no delay."
        )

    # --- Main content ---
    st.title("Alt Text Generator")
    st.caption("Upload CSV files to generate contextual alt text using Claude Vision API")

    # File upload (no duplicate label paragraph)
    uploaded_files = st.file_uploader(
        "Upload CSV and optional YAML config files",
        type=['csv', 'yaml'],
        accept_multiple_files=True,
        key='file_uploader'
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_path = WATCHED_DIR / uploaded_file.name
            with open(file_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())

        st.success(f"Uploaded {len(uploaded_files)} file(s)")
        scan_for_new_files()
        time.sleep(1)
        st.rerun()

    # --- Queue and processing ---
    queue = st.session_state.queue
    status = queue.get_queue_status()
    jobs = queue.get_all_jobs()

    # Only show queue metrics when there's something to show
    has_any_jobs = status['total_jobs'] > 0

    if has_any_jobs:
        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("Queued", status['queued'])
        col2.metric("Completed", status['completed'])
        col3.metric("Failed", status['failed'])

    # --- Cost estimate + confirmation for queued jobs ---
    current_job = queue.get_current_job()

    if not st.session_state.processing and not current_job:
        next_job = queue.get_next_job()
        if next_job:
            job_key = str(next_job.csv_path)

            if job_key not in st.session_state.confirmed_jobs:
                # Show cost estimate and ask for confirmation
                st.divider()
                st.subheader("Ready to Process")

                num_images, est_cost = estimate_job_cost(next_job.csv_path)

                col1, col2, col3 = st.columns(3)
                col1.metric("File", next_job.csv_path.name)
                col2.metric("Images to Process", num_images)
                col3.metric("Estimated Cost", f"${est_cost:.4f}")

                if not api_key_ok:
                    st.warning("Cannot start processing: API key is not configured. Check the sidebar.")
                elif num_images == 0:
                    st.info("No images need processing in this file. All rows already have alt text.")
                else:
                    if st.button("Start Processing", type="primary", use_container_width=True):
                        st.session_state.confirmed_jobs.add(job_key)
                        st.rerun()
            else:
                # Job confirmed, start processing
                process_next_job()

    # Current processing job
    if current_job:
        st.divider()
        st.subheader("Currently Processing")

        with st.container():
            st.info(f"**File:** {current_job.csv_path.name}")

            if st.session_state.current_status:
                st.write(f"**Status:** {st.session_state.current_status}")

            if current_job.started_at:
                elapsed = (datetime.now() - current_job.started_at).total_seconds()
                st.write(f"**Elapsed Time:** {elapsed:.1f}s")

    # --- Errors and Skipped (only shown when there's data) ---
    has_errors = bool(st.session_state.error_log)
    has_skipped = bool(st.session_state.skipped_log)

    if has_errors or has_skipped:
        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            if has_errors:
                st.subheader(f"Errors ({len(st.session_state.error_log)})")
                recent_errors = st.session_state.error_log[-10:]
                for error in reversed(recent_errors):
                    url_display = error['url'][:50] + '...' if len(error['url']) > 50 else error['url']
                    with st.expander(f"{error['job']} - {url_display}"):
                        st.error(f"**Error:** {error['error']}")
                        st.caption(f"Time: {error['timestamp'].strftime('%H:%M:%S')}")

        with col2:
            if has_skipped:
                st.subheader(f"Skipped Images ({len(st.session_state.skipped_log)})")
                recent_skipped = st.session_state.skipped_log[-10:]
                for skipped in reversed(recent_skipped):
                    url_display = skipped['url'][:50] + '...' if len(skipped['url']) > 50 else skipped['url']
                    with st.expander(f"{skipped['job']} - {url_display}"):
                        st.warning(f"**Reason:** {skipped['reason']}")
                        st.caption(f"Time: {skipped['timestamp'].strftime('%H:%M:%S')}")

    # --- Completed jobs (only shown when there's data) ---
    completed_jobs = [j for j in jobs if j.status == ProcessingStatus.COMPLETED]

    if completed_jobs:
        st.divider()
        st.subheader("Completed Jobs")

        for job in reversed(completed_jobs):
            with st.expander(f"{job.csv_path.name} - Completed at {job.completed_at.strftime('%H:%M:%S')}"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Processed", job.total_processed)
                col2.metric("Skipped", job.total_skipped)
                col3.metric("Failed", job.total_failed)
                col4.metric("Cost", f"${job.estimated_cost:.4f}")

                st.write("**Output Files:**")
                for output_file in job.output_files:
                    if output_file.exists():
                        with open(output_file, 'rb') as f:
                            file_data = f.read()

                        st.download_button(
                            label=f"Download {output_file.name}",
                            data=file_data,
                            file_name=output_file.name,
                            mime='text/csv',
                            key=f"download_{job.csv_path.name}_{output_file.name}"
                        )

    # --- Failed jobs (only shown when there's data) ---
    failed_jobs = [j for j in jobs if j.status == ProcessingStatus.FAILED]

    if failed_jobs:
        st.divider()
        st.subheader("Failed Jobs")

        for job in reversed(failed_jobs):
            with st.expander(f"{job.csv_path.name} - Failed"):
                st.error(f"**Error:** {job.error_message}")
                if job.started_at and job.completed_at:
                    duration = (job.completed_at - job.started_at).total_seconds()
                    st.write(f"**Duration:** {duration:.1f}s")

    # Auto-refresh if processing or if there are confirmed queued jobs
    if st.session_state.processing or status['queued'] > 0:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
