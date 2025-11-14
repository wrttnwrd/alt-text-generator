"""
Image Handler for Alt Text Generator
Downloads and processes images with size checking.
"""

import os
import requests
from PIL import Image
from io import BytesIO
from typing import Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
import hashlib


class ImageSizeCategory:
    """Image size categories for processing."""
    NORMAL = "normal"          # < 2000x2000
    LARGE = "large"            # 2000x2000 to 8000x8000
    TOO_LARGE = "too_large"    # > 8000x8000


class ImageHandler:
    """Handles image downloading and size checking."""

    def __init__(self, temp_dir: str = "temp_images", timeout: int = 30):
        """
        Initialize image handler.

        Args:
            temp_dir: Directory to store downloaded images
            timeout: Request timeout in seconds
        """
        self.temp_dir = temp_dir
        self.timeout = timeout
        os.makedirs(temp_dir, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def download_image(self, image_url: str) -> Tuple[Optional[str], Optional[str], Optional[Tuple[int, int]]]:
        """
        Download an image and determine its size category.

        Args:
            image_url: URL of the image to download

        Returns:
            Tuple of (local_path, size_category, dimensions) or (None, None, None) on error
            - local_path: Path to downloaded image file, or None if error
            - size_category: One of ImageSizeCategory constants, or None if error
            - dimensions: Tuple of (width, height), or None if error
        """
        try:
            # Download image
            response = self.session.get(image_url, timeout=self.timeout)
            response.raise_for_status()

            # Check file size (Claude Vision limit is 5MB)
            file_size_mb = len(response.content) / (1024 * 1024)
            MAX_FILE_SIZE_MB = 5.0

            if file_size_mb > MAX_FILE_SIZE_MB:
                size_category = ImageSizeCategory.TOO_LARGE
                return None, size_category, (0, 0)  # Return 0,0 as dimensions for file size issue

            # Load image to check dimensions
            image = Image.open(BytesIO(response.content))
            width, height = image.size

            # Determine size category
            max_dimension = max(width, height)
            if max_dimension > 8000:
                size_category = ImageSizeCategory.TOO_LARGE
                return None, size_category, (width, height)
            elif max_dimension > 2000:
                size_category = ImageSizeCategory.LARGE
            else:
                size_category = ImageSizeCategory.NORMAL

            # Generate filename from URL hash
            url_hash = hashlib.md5(image_url.encode()).hexdigest()
            file_extension = self._get_image_extension(image_url, image.format)
            local_filename = f"{url_hash}{file_extension}"
            local_path = os.path.join(self.temp_dir, local_filename)

            # Save image
            with open(local_path, 'wb') as f:
                f.write(response.content)

            return local_path, size_category, (width, height)

        except requests.exceptions.Timeout:
            return None, None, None
        except requests.exceptions.RequestException as e:
            return None, None, None
        except Exception as e:
            return None, None, None

    def _get_image_extension(self, url: str, format: Optional[str]) -> str:
        """
        Determine image file extension.

        Args:
            url: Image URL
            format: PIL image format

        Returns:
            File extension including dot
        """
        # Try to get from URL
        if '.' in url.split('/')[-1]:
            ext = '.' + url.split('.')[-1].split('?')[0].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                return ext

        # Use PIL format
        if format:
            format_lower = format.lower()
            if format_lower == 'jpeg':
                return '.jpg'
            return f'.{format_lower}'

        # Default
        return '.jpg'

    def get_image_base64(self, image_path: str) -> Optional[str]:
        """
        Read image and convert to base64 for Claude API.

        Args:
            image_path: Path to the image file

        Returns:
            Base64 encoded string, or None on error
        """
        try:
            import base64

            with open(image_path, 'rb') as f:
                image_data = f.read()

            return base64.standard_b64encode(image_data).decode('utf-8')

        except Exception as e:
            return None

    def get_image_media_type(self, image_path: str) -> str:
        """
        Determine media type for an image.

        Args:
            image_path: Path to the image file

        Returns:
            Media type string (e.g., 'image/jpeg')
        """
        ext = os.path.splitext(image_path)[1].lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp'
        }
        return media_types.get(ext, 'image/jpeg')

    def cleanup(self):
        """Remove all downloaded images."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            os.makedirs(self.temp_dir, exist_ok=True)
