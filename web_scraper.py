"""
Web Scraper for Alt Text Generator
Scrapes web pages to extract contextual information for images.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
import time


class ForbiddenError(Exception):
    """Raised when a 403 Forbidden error is encountered."""
    pass


class WebScraper:
    """Scrapes web pages for title, headings, and adjacent text."""

    def __init__(self, timeout: int = 30):
        """
        Initialize web scraper.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _fetch_page(self, url: str) -> Tuple[requests.Response, str]:
        """
        Fetch page content with retry logic.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (response, error_message)

        Raises:
            ForbiddenError: If 403 status is received
        """
        try:
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 403:
                raise ForbiddenError(f"403 Forbidden error for {url}")

            response.raise_for_status()
            return response, None

        except ForbiddenError:
            raise
        except requests.exceptions.Timeout:
            return None, "Timeout error"
        except requests.exceptions.ConnectionError:
            return None, "Connection error"
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP error: {e.response.status_code}"
        except Exception as e:
            return None, f"Error: {str(e)}"

    def scrape_page(self, page_url: str, image_urls: list) -> Dict[str, Dict[str, str]]:
        """
        Scrape a page for title, H1, and adjacent text for each image.

        Args:
            page_url: URL of the page to scrape
            image_urls: List of image URLs on this page

        Returns:
            Dictionary with page-level data and per-image data:
            {
                'page_data': {'title': str, 'h1': str, 'error': str or None},
                'images': {
                    'image_url': {'adjacent_text': str, 'error': str or None},
                    ...
                }
            }
        """
        result = {
            'page_data': {'title': '', 'h1': '', 'error': None},
            'images': {}
        }

        # Initialize image results
        for img_url in image_urls:
            result['images'][img_url] = {'adjacent_text': '', 'error': None}

        try:
            # Fetch the page
            response, error = self._fetch_page(page_url)

            if error or response is None:
                result['page_data']['error'] = error
                for img_url in image_urls:
                    result['images'][img_url]['error'] = error
                return result

            # Parse HTML
            soup = BeautifulSoup(response.content, 'lxml')

            # Extract title
            title_tag = soup.find('title')
            if title_tag:
                result['page_data']['title'] = title_tag.get_text(strip=True)

            # Extract H1
            h1_tag = soup.find('h1')
            if h1_tag:
                result['page_data']['h1'] = h1_tag.get_text(strip=True)

            # For each image, find adjacent text
            for img_url in image_urls:
                adjacent_text = self._find_adjacent_text(soup, img_url)
                result['images'][img_url]['adjacent_text'] = adjacent_text

        except ForbiddenError:
            raise
        except Exception as e:
            error_msg = f"Scraping error: {str(e)}"
            result['page_data']['error'] = error_msg
            for img_url in image_urls:
                result['images'][img_url]['error'] = error_msg

        return result

    def _find_adjacent_text(self, soup: BeautifulSoup, image_url: str) -> str:
        """
        Find adjacent text for a specific image.
        Looks for:
        1. Caption or figcaption wrapping the image
        2. Closest H2, H3, or H4 appearing before the image

        Args:
            soup: BeautifulSoup object of the page
            image_url: URL of the image to find text for

        Returns:
            Adjacent text string
        """
        adjacent_texts = []

        # Find all img tags that match this URL
        # Try both src and data-src attributes
        img_tags = soup.find_all('img', src=lambda x: x and image_url in x if x else False)
        if not img_tags:
            img_tags = soup.find_all('img', attrs={'data-src': lambda x: x and image_url in x if x else False})

        for img_tag in img_tags:
            # Check for figcaption in parent figure
            parent = img_tag.parent
            if parent and parent.name == 'figure':
                figcaption = parent.find('figcaption')
                if figcaption:
                    adjacent_texts.append(figcaption.get_text(strip=True))
                    continue

            # Check for caption class nearby
            caption = img_tag.find_next_sibling(['p', 'div', 'span'], class_=lambda x: x and 'caption' in x.lower() if x else False)
            if caption:
                adjacent_texts.append(caption.get_text(strip=True))
                continue

            # Find closest preceding heading (H2, H3, or H4)
            heading = self._find_preceding_heading(img_tag)
            if heading:
                adjacent_texts.append(heading.get_text(strip=True))

        # Return combined text or empty string
        return ' | '.join(adjacent_texts) if adjacent_texts else ''

    def _find_preceding_heading(self, element) -> Optional[BeautifulSoup]:
        """
        Find the closest H2, H3, or H4 heading that appears before the element in the DOM.

        Args:
            element: BeautifulSoup element to search from

        Returns:
            The heading element if found, None otherwise
        """
        # Get all previous siblings and their descendants
        current = element
        while current:
            # Check previous siblings
            for sibling in current.find_previous_siblings():
                # Check if sibling itself is a heading
                if sibling.name in ['h2', 'h3', 'h4']:
                    return sibling
                # Check if sibling contains headings
                headings = sibling.find_all(['h2', 'h3', 'h4'])
                if headings:
                    return headings[-1]  # Return the last (closest) one

            # Move up to parent
            current = current.parent
            if current and current.name == '[document]':
                break

        return None
