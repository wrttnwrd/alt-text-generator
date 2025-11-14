"""
CSV Handler for Alt Text Generator
Manages reading and writing CSV files with image and page data.
"""

import pandas as pd
from typing import Optional
import os


class CSVHandler:
    """Handles CSV operations for the alt text generator."""

    REQUIRED_COLUMNS = ['Source', 'Destination']
    NEW_COLUMNS = ['title tag', 'H1 tag', 'adjacent text', 'message', 'ALT text']

    def __init__(self, csv_path: str):
        """
        Initialize CSV handler.

        Args:
            csv_path: Path to the CSV file
        """
        self.csv_path = csv_path
        self.df: Optional[pd.DataFrame] = None

    def load(self) -> pd.DataFrame:
        """
        Load CSV file and add necessary columns if they don't exist.

        Returns:
            DataFrame with the loaded data

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If required columns are missing
        """
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        # Load CSV
        self.df = pd.read_csv(self.csv_path)

        # Verify required columns exist
        missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in self.df.columns]
        if missing_columns:
            raise ValueError(f"CSV missing required columns: {missing_columns}")

        # Add new columns if they don't exist
        for col in self.NEW_COLUMNS:
            if col not in self.df.columns:
                self.df[col] = ''

        return self.df

    def save(self):
        """Save the DataFrame back to the CSV file."""
        if self.df is None:
            raise ValueError("No data loaded. Call load() first.")

        self.df.to_csv(self.csv_path, index=False)

    def update_row(self, index: int, **kwargs):
        """
        Update specific columns in a row.

        Args:
            index: Row index to update
            **kwargs: Column name and value pairs to update
        """
        if self.df is None:
            raise ValueError("No data loaded. Call load() first.")

        for col, value in kwargs.items():
            if col in self.df.columns:
                # Convert value to string to avoid dtype issues, unless it's already a string or None
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    self.df.at[index, col] = ''
                else:
                    self.df.at[index, col] = str(value)

    def get_rows_to_process(self) -> pd.DataFrame:
        """
        Get rows that need processing (those without ALT text).

        Returns:
            DataFrame containing only rows that need processing
        """
        if self.df is None:
            raise ValueError("No data loaded. Call load() first.")

        # Return rows where ALT text is empty or null
        return self.df[self.df['ALT text'].isna() | (self.df['ALT text'] == '')]

    def get_unique_pages(self) -> list:
        """
        Get list of unique source pages that need processing.

        Returns:
            List of unique source page URLs
        """
        if self.df is None:
            raise ValueError("No data loaded. Call load() first.")

        rows_to_process = self.get_rows_to_process()
        return rows_to_process['Source'].unique().tolist()

    def get_images_for_page(self, page_url: str) -> pd.DataFrame:
        """
        Get all image rows for a specific page.

        Args:
            page_url: The source page URL

        Returns:
            DataFrame containing all rows for the specified page
        """
        if self.df is None:
            raise ValueError("No data loaded. Call load() first.")

        return self.df[self.df['Source'] == page_url]
