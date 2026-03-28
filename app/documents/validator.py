"""PDF document validation service enforcing size, format, and structure rules."""

import io
import logging
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

PDF_MAGIC_BYTES = b"%PDF-"


class DocumentValidator:
    """Validator ensuring uploaded files are legitimate, bounded PDF documents."""

    @staticmethod
    def validate_pdf(
        content: bytes,
        original_filename: str,
        content_type: str | None = None,
        max_size_mb: int = 10,
    ) -> int:
        """Validate an uploaded PDF file and return its page count.

        Args:
            content: Raw byte content of the file.
            original_filename: Filename supplied by client.
            content_type: MIME type reported by the client.
            max_size_mb: Configured maximum size in megabytes.

        Returns:
            Total page count of the valid PDF.

        Raises:
            ValueError: If the file fails any size, signature, or structural check.
        """
        # 1. Non-empty check
        if not content or len(content) == 0:
            raise ValueError("Uploaded file is empty.")

        # 2. File size bound
        max_bytes = max_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(
                f"File size exceeds the maximum permitted limit of {max_size_mb} MB."
            )

        # 3. Filename extension validation
        if not original_filename.lower().endswith(".pdf"):
            raise ValueError("Invalid file extension. Only .pdf files are supported.")

        # 4. Content-Type check (if provided)
        if content_type and "pdf" not in content_type.lower():
            raise ValueError(
                f"Invalid MIME content type '{content_type}'. Must be application/pdf."
            )

        # 5. PDF Magic Bytes / Signature validation
        if not content.startswith(PDF_MAGIC_BYTES):
            raise ValueError(
                "Invalid PDF file signature. File header does not match '%PDF-'."
            )

        # 6. Parse PDF structure and verify it is not corrupted
        try:
            reader = PdfReader(io.BytesIO(content))
            page_count = len(reader.pages)
        except PdfReadError as exc:
            logger.warning("Corrupted PDF detected during validation: %s", exc)
            raise ValueError("Malformed or corrupt PDF document.") from exc
        except Exception as exc:
            logger.warning("Unexpected error parsing PDF: %s", exc)
            raise ValueError("Failed to parse PDF document structure.") from exc

        if page_count == 0:
            raise ValueError("PDF document contains zero pages.")

        return page_count
