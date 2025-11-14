"""
Alt Text Generator using Claude Vision API
Generates alt text for images using contextual information.
"""

import anthropic
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import time


class AltTextGenerator:
    """Generates alt text using Claude Vision API."""

    MODEL = "claude-sonnet-4-5-20250929"
    MAX_TOKENS = 300
    BATCH_SIZE = 8  # Process 8 images per API call for optimal performance

    def __init__(self, api_key: str, instructions: Optional[str] = None):
        """
        Initialize alt text generator.

        Args:
            api_key: Anthropic API key
            instructions: Optional custom instructions from markdown file
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.instructions = instructions or ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30)
    )
    def generate_batch(self, image_data: List[Dict]) -> List[Dict]:
        """
        Generate alt text for a batch of images.

        Args:
            image_data: List of dictionaries containing:
                - 'image_base64': Base64 encoded image
                - 'media_type': Image media type (e.g., 'image/jpeg')
                - 'title': Page title
                - 'h1': Page H1
                - 'adjacent_text': Adjacent heading or caption
                - 'image_url': Original image URL (for reference)

        Returns:
            List of dictionaries with 'image_url' and 'alt_text' keys
        """
        if not image_data:
            return []

        # Build the prompt
        system_prompt = self._build_system_prompt()
        user_content = self._build_user_content(image_data)

        try:
            # Call Claude API
            message = self.client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS * len(image_data),
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_content
                    }
                ]
            )

            # Parse response
            response_text = message.content[0].text
            results = self._parse_response(response_text, image_data)

            return results

        except anthropic.RateLimitError as e:
            # Wait longer for rate limits
            time.sleep(60)
            raise
        except Exception as e:
            # Return error for all images in batch
            return [
                {'image_url': img['image_url'], 'alt_text': None, 'error': str(e)}
                for img in image_data
            ]

    def _build_system_prompt(self) -> str:
        """Build the system prompt for Claude."""
        base_prompt = """You are an expert at writing accessible, SEO-friendly alt text for images.

Your task is to generate concise, descriptive alt text that:
1. Accurately describes the visual content of the image
2. Considers the context of the page (title, headings, adjacent text)
3. Is concise (typically 1-2 sentences, max 125 characters when possible)
4. Follows web accessibility best practices
5. Avoids redundant phrases like "image of" or "picture of"
6. Focuses on what's important and relevant to the page context"""

        if self.instructions:
            base_prompt += f"\n\nAdditional instructions for this website:\n{self.instructions}"

        return base_prompt

    def _build_user_content(self, image_data: List[Dict]) -> List[Dict]:
        """
        Build the user content with images and context.

        Args:
            image_data: List of image data dictionaries

        Returns:
            List of content blocks for the API
        """
        content = []

        # Add introductory text
        intro_text = f"Please generate alt text for the following {len(image_data)} image(s). "
        intro_text += "For each image, provide ONLY the alt text on a single line, "
        intro_text += "in the format 'Image 1:', 'Image 2:', etc.\n\n"

        content.append({
            "type": "text",
            "text": intro_text
        })

        # Add each image with its context
        for i, img in enumerate(image_data, 1):
            # Add context text
            context_parts = []
            if img.get('title'):
                context_parts.append(f"Page title: {img['title']}")
            if img.get('h1'):
                context_parts.append(f"Page heading: {img['h1']}")
            if img.get('adjacent_text'):
                context_parts.append(f"Adjacent text: {img['adjacent_text']}")

            context_text = f"\n--- Image {i} Context ---\n"
            if context_parts:
                context_text += "\n".join(context_parts) + "\n"
            else:
                context_text += "No additional context available.\n"

            content.append({
                "type": "text",
                "text": context_text
            })

            # Add image
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img['media_type'],
                    "data": img['image_base64']
                }
            })

        # Add closing instruction
        content.append({
            "type": "text",
            "text": "\n\nPlease provide the alt text for each image, one per line, in the format: 'Image 1: [alt text]'"
        })

        return content

    def _parse_response(self, response_text: str, image_data: List[Dict]) -> List[Dict]:
        """
        Parse Claude's response to extract alt text for each image.

        Args:
            response_text: Response from Claude
            image_data: Original image data for mapping

        Returns:
            List of results with alt text
        """
        results = []
        lines = response_text.strip().split('\n')

        # Try to match each line to an image
        alt_texts = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for "Image N:" pattern
            for i in range(1, len(image_data) + 1):
                prefix = f"Image {i}:"
                if line.startswith(prefix):
                    alt_text = line[len(prefix):].strip()
                    alt_texts[i-1] = alt_text
                    break

        # Map alt texts to images
        for i, img in enumerate(image_data):
            alt_text = alt_texts.get(i)
            results.append({
                'image_url': img['image_url'],
                'alt_text': alt_text,
                'error': None if alt_text else 'Failed to parse alt text from response'
            })

        return results

    @staticmethod
    def estimate_cost(num_images: int, avg_image_size_kb: int = 500) -> float:
        """
        Estimate the cost of processing images.

        Args:
            num_images: Number of images to process
            avg_image_size_kb: Average image size in KB

        Returns:
            Estimated cost in USD

        Note: Pricing for claude-3-5-sonnet-20241022:
            - Input: $3 per million tokens
            - Output: $15 per million tokens
            - Images: ~1 token per ~0.75KB (approximate)
        """
        # Approximate token usage
        tokens_per_image = (avg_image_size_kb / 0.75)  # Image tokens
        tokens_per_image += 200  # Context text tokens
        output_tokens_per_image = 50  # Alt text output

        total_input_tokens = num_images * tokens_per_image
        total_output_tokens = num_images * output_tokens_per_image

        # Calculate cost
        input_cost = (total_input_tokens / 1_000_000) * 3
        output_cost = (total_output_tokens / 1_000_000) * 15

        return input_cost + output_cost
