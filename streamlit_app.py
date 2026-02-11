"""
Streamlit app for alt text generation with file watching and queue management.

Run with: streamlit run streamlit_app.py
"""

import streamlit as st
import time
from pathlib import Path
from datetime import datetime
import pandas as pd

from processing_queue import ProcessingQueue, ProcessingStatus, ProcessingJob
from config_handler import ProcessingConfig
from processor import process_csv_file


# Configuration
WATCHED_DIR = Path("watched")
OUTPUT_DIR = Path("output")


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
    progress_bar = st.progress(0)

    try:
        # Load configuration
        config = ProcessingConfig.from_csv_path(job.csv_path)

        status_container.info(f"Loading configuration for {job.csv_path.name}...")

        # Progress callback
        def on_progress(event_type: str, data: dict):
            if event_type == 'image_processed':
                pass  # Could update progress bar here
            elif event_type == 'image_skipped':
                st.session_state.skipped_log.append({
                    'job': job.csv_path.name,
                    'url': data['url'],
                    'reason': data['reason'],
                    'timestamp': datetime.now()
                })
            elif event_type == 'image_failed':
                st.session_state.error_log.append({
                    'job': job.csv_path.name,
                    'url': data['url'],
                    'error': data['error'],
                    'timestamp': datetime.now()
                })

        # Status callback
        def on_status(msg: str):
            st.session_state.current_status = msg
            status_container.info(f"**{job.csv_path.name}:** {msg}")

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

        status_container.success(f"✓ Completed: {job.csv_path.name}")
        progress_bar.progress(1.0)

    except Exception as e:
        # Mark as failed
        queue.mark_failed(job, str(e))
        st.session_state.error_log.append({
            'job': job.csv_path.name,
            'url': 'N/A',
            'error': str(e),
            'timestamp': datetime.now()
        })
        status_container.error(f"❌ Failed: {job.csv_path.name} - {str(e)}")

    finally:
        # Cleanup processed files
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

    # Scan for new files on each run
    scan_for_new_files()

    # Header
    st.title("🖼️ Alt Text Generator")
    st.markdown("Upload CSV files to generate contextual alt text using Claude Vision API")

    # File upload section
    st.header("📁 Upload Files")

    uploaded_files = st.file_uploader(
        "Drag and drop CSV files here (optional YAML files with same name for config)",
        type=['csv', 'yaml'],
        accept_multiple_files=True,
        key='file_uploader'
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_path = WATCHED_DIR / uploaded_file.name
            with open(file_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())

        st.success(f"✓ Uploaded {len(uploaded_files)} file(s) to watched folder")
        time.sleep(1)
        st.rerun()

    # Queue status
    st.header("📊 Processing Queue")

    queue = st.session_state.queue
    status = queue.get_queue_status()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Jobs", status['total_jobs'])
    col2.metric("Queued", status['queued'])
    col3.metric("Processing", status['processing'])
    col4.metric("Completed", status['completed'])
    col5.metric("Failed", status['failed'])

    # Process next job if not currently processing
    current_job = queue.get_current_job()

    if not current_job and not st.session_state.processing:
        # Check for next job
        next_job = queue.get_next_job()
        if next_job:
            process_next_job()
            st.rerun()

    # Current processing job
    if current_job:
        st.subheader("⚙️ Currently Processing")

        with st.container():
            st.info(f"**File:** {current_job.csv_path.name}")

            if st.session_state.current_status:
                st.write(f"**Status:** {st.session_state.current_status}")

            if current_job.started_at:
                elapsed = (datetime.now() - current_job.started_at).total_seconds()
                st.write(f"**Elapsed Time:** {elapsed:.1f}s")

    # Error and skipped logs
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("⚠️ Errors")

        if st.session_state.error_log:
            # Show last 10 errors
            recent_errors = st.session_state.error_log[-10:]

            for error in reversed(recent_errors):
                with st.expander(f"{error['job']} - {error['url'][:50]}..."):
                    st.error(f"**Error:** {error['error']}")
                    st.caption(f"Time: {error['timestamp'].strftime('%H:%M:%S')}")
        else:
            st.success("No errors")

    with col2:
        st.subheader("⏭️ Skipped Images")

        if st.session_state.skipped_log:
            # Show last 10 skipped
            recent_skipped = st.session_state.skipped_log[-10:]

            for skipped in reversed(recent_skipped):
                with st.expander(f"{skipped['job']} - {skipped['url'][:50]}..."):
                    st.warning(f"**Reason:** {skipped['reason']}")
                    st.caption(f"Time: {skipped['timestamp'].strftime('%H:%M:%S')}")
        else:
            st.success("No skipped images")

    # Completed jobs
    st.header("✅ Completed Jobs")

    jobs = queue.get_all_jobs()
    completed_jobs = [j for j in jobs if j.status == ProcessingStatus.COMPLETED]

    if completed_jobs:
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
                        # Read file content for download
                        with open(output_file, 'rb') as f:
                            file_data = f.read()

                        # Create download button
                        st.download_button(
                            label=f"📥 Download {output_file.name}",
                            data=file_data,
                            file_name=output_file.name,
                            mime='text/csv',
                            key=f"download_{job.csv_path.name}_{output_file.name}"
                        )
    else:
        st.info("No completed jobs yet")

    # Failed jobs
    failed_jobs = [j for j in jobs if j.status == ProcessingStatus.FAILED]

    if failed_jobs:
        st.header("❌ Failed Jobs")

        for job in reversed(failed_jobs):
            with st.expander(f"{job.csv_path.name} - Failed"):
                st.error(f"**Error:** {job.error_message}")
                if job.started_at and job.completed_at:
                    duration = (job.completed_at - job.started_at).total_seconds()
                    st.write(f"**Duration:** {duration:.1f}s")

    # Auto-refresh if processing or if there are queued jobs
    if st.session_state.processing or status['queued'] > 0:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
