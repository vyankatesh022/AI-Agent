"""PDF text extraction and cleaning service with page boundary preservation."""

import io
import logging
import re
from pypdf import PdfReader

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Extracts and sanitizes text from validated PDF files while preserving page numbers."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Sanitize raw extracted text.

        - Removes null bytes and unprintable control characters.
        - Normalizes horizontal whitespace (collapses multiple spaces/tabs into one).
        - Collapses excessive newlines (maximum of 2 consecutive newlines).
        - Strips surrounding whitespace.
        """
        if not text:
            return ""

        # Remove null characters and non-printable control characters except \n, \r, \t
        sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Normalize line endings
        sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse horizontal whitespace within lines
        sanitized = re.sub(r"[ \t]+", " ", sanitized)

        # Collapse excessive newlines (> 2 newlines -> 2 newlines)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

        return sanitized.strip()

    @classmethod
    def extract_pages(cls, content: bytes) -> list[tuple[int, str]]:
        """Extract text from PDF bytes page by page.

        Args:
            content: Raw byte content of the PDF.

        Returns:
            List of tuples (page_number, cleaned_page_text) where page_number is 1-indexed.

        Raises:
            ValueError: If the PDF contains no extractable text (e.g. image-only / scanned PDF).
        """
        reader = PdfReader(io.BytesIO(content))
        extracted_pages: list[tuple[int, str]] = []
        total_text_length = 0

        for page_idx, page in enumerate(reader.pages):
            page_number = page_idx + 1
            raw_text = page.extract_text() or ""
            cleaned = cls.clean_text(raw_text)
            extracted_pages.append((page_number, cleaned))
            total_text_length += len(cleaned)

        if total_text_length == 0:
            raise ValueError(
                "Document contains no extractable text. "
                "Scanned or image-only PDFs without OCR are not supported."
            )

        logger.debug(
            "Extracted text from %d pages (total characters: %d)",
            len(extracted_pages),
            total_text_length,
        )
        return extracted_pages
