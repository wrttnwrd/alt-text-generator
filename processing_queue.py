"""
Processing queue manager for handling CSV files one at a time.

Manages the queue of CSV files to process, tracking their status,
and coordinating the processing workflow.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import time


class ProcessingStatus(Enum):
    """Status of a CSV file in the processing queue."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    """Represents a single CSV file processing job."""
    csv_path: Path
    yaml_path: Optional[Path] = None
    status: ProcessingStatus = ProcessingStatus.QUEUED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Processing results
    total_processed: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    estimated_cost: float = 0.0

    # Output files
    output_files: List[Path] = field(default_factory=list)

    def __post_init__(self):
        """Check for matching YAML file."""
        if self.yaml_path is None:
            potential_yaml = self.csv_path.with_suffix('.yaml')
            if potential_yaml.exists():
                self.yaml_path = potential_yaml


class ProcessingQueue:
    """Manages a queue of CSV files to process."""

    def __init__(self, watched_dir: Path, output_dir: Path):
        """
        Initialize the processing queue.

        Args:
            watched_dir: Directory to watch for CSV files
            output_dir: Directory where output files will be placed
        """
        self.watched_dir = Path(watched_dir)
        self.output_dir = Path(output_dir)
        self.jobs: List[ProcessingJob] = []
        self._lock = threading.Lock()

        # Ensure directories exist
        self.watched_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    def scan_for_new_files(self) -> List[Path]:
        """
        Scan the watched directory for new CSV files.

        Returns:
            List of new CSV file paths not yet in the queue
        """
        csv_files = list(self.watched_dir.glob("*.csv"))

        # Filter out files already in queue
        with self._lock:
            existing_paths = {job.csv_path for job in self.jobs}

        new_files = [f for f in csv_files if f not in existing_paths]
        return new_files

    def add_job(self, csv_path: Path) -> ProcessingJob:
        """
        Add a new job to the queue.

        Args:
            csv_path: Path to the CSV file to process

        Returns:
            The created ProcessingJob
        """
        job = ProcessingJob(csv_path=csv_path)

        with self._lock:
            self.jobs.append(job)

        return job

    def get_next_job(self) -> Optional[ProcessingJob]:
        """
        Get the next queued job to process.

        Returns:
            Next job with QUEUED status, or None if no jobs are queued
        """
        with self._lock:
            for job in self.jobs:
                if job.status == ProcessingStatus.QUEUED:
                    return job
        return None

    def get_current_job(self) -> Optional[ProcessingJob]:
        """
        Get the currently processing job.

        Returns:
            Job with PROCESSING status, or None if no job is processing
        """
        with self._lock:
            for job in self.jobs:
                if job.status == ProcessingStatus.PROCESSING:
                    return job
        return None

    def mark_processing(self, job: ProcessingJob) -> None:
        """Mark a job as currently processing."""
        with self._lock:
            job.status = ProcessingStatus.PROCESSING
            job.started_at = datetime.now()

    def mark_completed(self, job: ProcessingJob, results: Dict[str, Any]) -> None:
        """
        Mark a job as completed with results.

        Args:
            job: The completed job
            results: Dictionary containing processing results:
                - total_processed: Number of images processed
                - total_skipped: Number of images skipped
                - total_failed: Number of images failed
                - estimated_cost: Estimated API cost
                - output_files: List of generated output file paths
        """
        with self._lock:
            job.status = ProcessingStatus.COMPLETED
            job.completed_at = datetime.now()
            job.total_processed = results.get('total_processed', 0)
            job.total_skipped = results.get('total_skipped', 0)
            job.total_failed = results.get('total_failed', 0)
            job.estimated_cost = results.get('estimated_cost', 0.0)
            job.output_files = results.get('output_files', [])

    def mark_failed(self, job: ProcessingJob, error_message: str) -> None:
        """Mark a job as failed with an error message."""
        with self._lock:
            job.status = ProcessingStatus.FAILED
            job.completed_at = datetime.now()
            job.error_message = error_message

    def cleanup_completed_jobs(self) -> None:
        """
        Remove processed CSV and YAML files from the watched directory.
        Only cleans up jobs with COMPLETED status.
        """
        with self._lock:
            for job in self.jobs:
                if job.status == ProcessingStatus.COMPLETED:
                    # Remove CSV file
                    if job.csv_path.exists():
                        job.csv_path.unlink()

                    # Remove YAML file if it exists
                    if job.yaml_path and job.yaml_path.exists():
                        job.yaml_path.unlink()

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status.

        Returns:
            Dictionary with queue statistics
        """
        with self._lock:
            return {
                'total_jobs': len(self.jobs),
                'queued': sum(1 for j in self.jobs if j.status == ProcessingStatus.QUEUED),
                'processing': sum(1 for j in self.jobs if j.status == ProcessingStatus.PROCESSING),
                'completed': sum(1 for j in self.jobs if j.status == ProcessingStatus.COMPLETED),
                'failed': sum(1 for j in self.jobs if j.status == ProcessingStatus.FAILED),
            }

    def get_all_jobs(self) -> List[ProcessingJob]:
        """Get a copy of all jobs in the queue."""
        with self._lock:
            return self.jobs.copy()
