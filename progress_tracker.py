"""
Progress Tracker for Alt Text Generator
Tracks and displays processing progress.
"""

import time
from typing import Optional


class ProgressTracker:
    """Tracks and displays progress of image processing."""

    def __init__(self, total_images: int):
        """
        Initialize progress tracker.

        Args:
            total_images: Total number of images to process
        """
        self.total_images = total_images
        self.processed_images = 0
        self.skipped_images = 0
        self.failed_images = 0
        self.start_time = time.time()
        self.last_processed_index = -1
        self.estimated_cost = 0.0
        self.actual_cost = 0.0

    def update(self, processed: int = 0, skipped: int = 0, failed: int = 0, last_index: int = None):
        """
        Update progress counters.

        Args:
            processed: Number of images processed
            skipped: Number of images skipped
            failed: Number of images failed
            last_index: Last processed row index
        """
        self.processed_images += processed
        self.skipped_images += skipped
        self.failed_images += failed

        if last_index is not None:
            self.last_processed_index = last_index

    def display(self):
        """Display current progress."""
        elapsed = time.time() - self.start_time
        total_done = self.processed_images + self.skipped_images + self.failed_images
        remaining = self.total_images - total_done

        # Calculate rate and ETA
        if total_done > 0 and elapsed > 0:
            rate = total_done / elapsed
            eta_seconds = remaining / rate if rate > 0 else 0
            eta_str = self._format_time(eta_seconds)
        else:
            eta_str = "calculating..."

        # Build progress message
        percent = (total_done / self.total_images * 100) if self.total_images > 0 else 0

        print(f"\r[{total_done}/{self.total_images}] {percent:.1f}% | "
              f"✓ {self.processed_images} processed | "
              f"↷ {self.skipped_images} skipped | "
              f"✗ {self.failed_images} failed | "
              f"ETA: {eta_str}", end='', flush=True)

    def display_summary(self):
        """Display final summary."""
        elapsed = time.time() - self.start_time
        elapsed_str = self._format_time(elapsed)

        print("\n")
        print("=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)
        print(f"Total images:      {self.total_images}")
        print(f"Successfully processed: {self.processed_images}")
        print(f"Skipped:          {self.skipped_images}")
        print(f"Failed:           {self.failed_images}")
        print(f"Time elapsed:     {elapsed_str}")

        if self.estimated_cost > 0:
            print(f"Estimated cost:   ${self.estimated_cost:.4f}")

        if self.last_processed_index >= 0:
            print(f"\nLast processed row index: {self.last_processed_index}")
            print("(Use this to resume if needed)")

        print("=" * 60)

    def display_interrupt_summary(self):
        """Display summary when interrupted."""
        elapsed = time.time() - self.start_time
        elapsed_str = self._format_time(elapsed)
        total_done = self.processed_images + self.skipped_images + self.failed_images

        print("\n")
        print("=" * 60)
        print("PROCESSING INTERRUPTED")
        print("=" * 60)
        print(f"Progress:         {total_done}/{self.total_images} images")
        print(f"Successfully processed: {self.processed_images}")
        print(f"Skipped:          {self.skipped_images}")
        print(f"Failed:           {self.failed_images}")
        print(f"Time elapsed:     {elapsed_str}")

        if self.last_processed_index >= 0:
            print(f"\nLast processed row index: {self.last_processed_index}")
            print("Resume by running the script again with the same CSV.")
            print("Rows with existing ALT text will be automatically skipped.")

        print("=" * 60)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        Format seconds into human-readable time.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
