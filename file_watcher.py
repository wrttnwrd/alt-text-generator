"""
File watcher for monitoring the watched directory for new CSV files.

Uses the watchdog library to detect when new CSV files are added
to the watched directory and automatically adds them to the processing queue.
"""

import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from typing import Callable


class CSVFileHandler(FileSystemEventHandler):
    """Handles file system events for CSV files."""

    def __init__(self, on_new_csv: Callable[[Path], None]):
        """
        Initialize the CSV file handler.

        Args:
            on_new_csv: Callback function to call when a new CSV is detected.
                        Takes the CSV file path as an argument.
        """
        super().__init__()
        self.on_new_csv = on_new_csv
        self._processed_files = set()

    def _is_csv_file(self, path: str) -> bool:
        """Check if the path is a CSV file."""
        return path.lower().endswith('.csv')

    def _handle_csv_file(self, csv_path: Path) -> None:
        """
        Handle a new CSV file.

        Args:
            csv_path: Path to the CSV file
        """
        # Avoid processing the same file multiple times
        abs_path = csv_path.absolute()
        if abs_path in self._processed_files:
            return

        self._processed_files.add(abs_path)

        # Wait a moment to ensure file write is complete
        time.sleep(0.5)

        # Call the callback
        self.on_new_csv(csv_path)

    def on_created(self, event):
        """Called when a file or directory is created."""
        if event.is_directory:
            return

        if self._is_csv_file(event.src_path):
            csv_path = Path(event.src_path)
            self._handle_csv_file(csv_path)

    def on_moved(self, event):
        """Called when a file or directory is moved or renamed."""
        if event.is_directory:
            return

        # Handle files moved INTO the watched directory
        if self._is_csv_file(event.dest_path):
            csv_path = Path(event.dest_path)
            self._handle_csv_file(csv_path)


class DirectoryWatcher:
    """Watches a directory for new CSV files."""

    def __init__(self, watched_dir: Path, on_new_csv: Callable[[Path], None]):
        """
        Initialize the directory watcher.

        Args:
            watched_dir: Directory to watch
            on_new_csv: Callback function to call when a new CSV is detected
        """
        self.watched_dir = Path(watched_dir)
        self.on_new_csv = on_new_csv

        # Ensure directory exists
        self.watched_dir.mkdir(exist_ok=True)

        # Set up watchdog
        self.event_handler = CSVFileHandler(on_new_csv)
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            str(self.watched_dir),
            recursive=False
        )

    def start(self) -> None:
        """Start watching the directory."""
        self.observer.start()

    def stop(self) -> None:
        """Stop watching the directory."""
        self.observer.stop()
        self.observer.join()

    def scan_existing_files(self) -> None:
        """Scan for existing CSV files in the watched directory."""
        csv_files = list(self.watched_dir.glob("*.csv"))
        for csv_file in csv_files:
            self.on_new_csv(csv_file)
