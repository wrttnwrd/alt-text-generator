"""
Configuration handler for YAML-based per-file settings.

Supports reading YAML configuration files that map to command-line arguments:
- instructions: Custom instructions (inline markdown text)
- max_cost: Maximum cost limit in USD
- scrape_delay: Delay in seconds between page scrapes
- restart: Clear existing alt text and start fresh
"""

import yaml
import os
from pathlib import Path
from typing import Optional, Dict, Any


class ProcessingConfig:
    """Configuration for processing a single CSV file."""

    def __init__(
        self,
        instructions: Optional[str] = None,
        max_cost: Optional[float] = None,
        scrape_delay: Optional[float] = None,
        restart: bool = False
    ):
        self.instructions = instructions
        self.max_cost = max_cost
        self.scrape_delay = scrape_delay
        self.restart = restart

    @classmethod
    def from_yaml_file(cls, yaml_path: Path) -> 'ProcessingConfig':
        """
        Load configuration from a YAML file.

        Args:
            yaml_path: Path to the YAML configuration file

        Returns:
            ProcessingConfig instance with loaded settings

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"YAML config file not found: {yaml_path}")

        with open(yaml_path, 'r') as f:
            config_data = yaml.safe_load(f) or {}

        return cls(
            instructions=config_data.get('instructions'),
            max_cost=config_data.get('max_cost'),
            scrape_delay=config_data.get('scrape_delay'),
            restart=config_data.get('restart', False)
        )

    @classmethod
    def from_csv_path(cls, csv_path: Path) -> 'ProcessingConfig':
        """
        Load configuration for a CSV file by looking for a matching YAML file.

        If a YAML file with the same name exists (e.g., iowa.yaml for iowa.csv),
        load settings from it. Otherwise, return default configuration.

        Args:
            csv_path: Path to the CSV file being processed

        Returns:
            ProcessingConfig instance (either from YAML or defaults)
        """
        yaml_path = csv_path.with_suffix('.yaml')

        if yaml_path.exists():
            return cls.from_yaml_file(yaml_path)
        else:
            # Return default configuration
            return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary format."""
        return {
            'instructions': self.instructions,
            'max_cost': self.max_cost,
            'scrape_delay': self.scrape_delay,
            'restart': self.restart
        }

    def __repr__(self) -> str:
        return f"ProcessingConfig(instructions={'present' if self.instructions else 'none'}, max_cost={self.max_cost}, scrape_delay={self.scrape_delay}, restart={self.restart})"
