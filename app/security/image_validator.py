"""Authoritative backend image validator enforcing MIME, magic-byte, and dimensional security."""

import base64
import binascii
import logging
import re
import struct
from dataclasses import dataclass

from app.config import get_settings
from app.security.errors import AppSecurityException, ErrorCode

logger = logging.getLogger(__name__)

# Valid data URL regex: data:image/(jpeg|png|webp);base64,...
DATA_URL_PATTERN = re.compile(
    r"^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


class ImageValidationError(AppSecurityException):
    """Raised when an uploaded image violates format, size, or dimensional security policies."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )


@dataclass
class ValidatedImage:
    """Sanitized and verified image metadata and payload."""

    mime_type: str
    data_url: str
    size_bytes: int
    width: int
    height: int


class ImageValidator:
    """Enforces strict backend image verification.

    Defensive controls:
    1. MIME allowlist restriction: Only image/jpeg, image/png, image/webp.
    2. Size bounding: Upper limit defined by MAX_IMAGE_SIZE_MB (default: 10MB).
    3. Magic byte inspection: Ensures binary content matches declared MIME (anti-spoofing).
    4. Dimension bounds: Rejects images with dimensions exceeding MAX_IMAGE_DIMENSION.
    """

    SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

    @classmethod
    def parse_dimensions(cls, mime_type: str, data: bytes) -> tuple[int, int]:
        """Extract width and height from raw image headers without heavy external libraries.

        Returns:
            Tuple of (width, height) in pixels.
        """
        if mime_type == "image/png":
            if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", data[16:24])
                return int(w), int(h)

        elif mime_type == "image/jpeg":
            if len(data) >= 4 and data[:2] == b"\xff\xd8":
                idx = 2
                while idx < len(data) - 9:
                    if data[idx] != 0xFF:
                        idx += 1
                        continue
                    marker = data[idx + 1]
                    # Start of Frame markers (Baseline, Progressive DCT, etc.)
                    if marker in (
                        0xC0,
                        0xC1,
                        0xC2,
                        0xC3,
                        0xC5,
                        0xC6,
                        0xC7,
                        0xC9,
                        0xCA,
                        0xCB,
                        0xCD,
                        0xCE,
                        0xCF,
                    ):
                        h, w = struct.unpack(">HH", data[idx + 5 : idx + 9])
                        return int(w), int(h)
                    if idx + 4 > len(data):
                        break
                    length = struct.unpack(">H", data[idx + 2 : idx + 4])[0]
                    idx += 2 + length

        elif mime_type == "image/webp":
            if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                chunk = data[12:16]
                if chunk == b"VP8 ":
                    if len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
                        w, h = struct.unpack("<HH", data[26:30])
                        return int(w & 0x3FFF), int(h & 0x3FFF)
                elif chunk == b"VP8L":
                    if len(data) >= 25 and data[20] == 0x2F:
                        b1, b2, b3, b4 = data[21:25]
                        w = 1 + (((b2 & 0x3F) << 8) | b1)
                        h = 1 + (((b4 & 0xF) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                        return int(w), int(h)
                elif chunk == b"VP8X":
                    if len(data) >= 30:
                        w = 1 + struct.unpack("<I", data[24:27] + b"\x00")[0]
                        h = 1 + struct.unpack("<I", data[27:30] + b"\x00")[0]
                        return int(w), int(h)

        # Fallback default if header was non-standard but valid
        return 0, 0

    @classmethod
    def verify_magic_bytes(cls, declared_mime: str, data: bytes) -> bool:
        """Inspect binary stream magic signature to detect MIME spoofing."""
        if not data:
            return False

        if declared_mime == "image/jpeg":
            return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"
        elif declared_mime == "image/png":
            return len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n"
        elif declared_mime == "image/webp":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"

        return False

    @classmethod
    def validate(cls, image_input: str) -> ValidatedImage:
        """Validate, decode, and verify incoming image data URL.

        Args:
            image_input: Base64 data URL string (e.g., 'data:image/jpeg;base64,...').

        Returns:
            ValidatedImage containing normalized data URL and validated metadata.

        Raises:
            ImageValidationError: If image violates any validation policy.
        """
        settings = get_settings()

        if not image_input or not isinstance(image_input, str):
            raise ImageValidationError("Image input must be a non-empty string.")

        # 1. Parse data URL format
        match = DATA_URL_PATTERN.match(image_input.strip())
        if not match:
            # Check if it was sent as raw base64 without data URI prefix
            # We enforce explicit standard data URI format for unambiguous MIME handling
            raise ImageValidationError(
                "Image must be provided as a standard data URL (e.g., 'data:image/jpeg;base64,...'). "
                f"Supported types: {', '.join(sorted(cls.SUPPORTED_MIME_TYPES))}"
            )

        declared_mime = match.group(1).lower()
        raw_b64 = match.group(2).strip()

        # 2. Check MIME allowlist
        if declared_mime not in cls.SUPPORTED_MIME_TYPES:
            raise ImageValidationError(
                f"Unsupported image MIME type '{declared_mime}'. "
                f"Allowed: {', '.join(sorted(cls.SUPPORTED_MIME_TYPES))}"
            )

        # 3. Decode base64
        try:
            image_bytes = base64.b64decode(raw_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageValidationError(
                "Failed to decode image: payload contains invalid base64 data."
            ) from exc

        # 4. Check decoded size
        size_bytes = len(image_bytes)
        max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            raise ImageValidationError(
                f"Image size ({size_bytes / (1024 * 1024):.1f} MB) exceeds maximum allowed limit "
                f"of {settings.MAX_IMAGE_SIZE_MB} MB."
            )

        # 5. Magic byte verification (MIME spoofing defense)
        if not cls.verify_magic_bytes(declared_mime, image_bytes):
            raise ImageValidationError(
                f"Image content does not match declared MIME type '{declared_mime}'. "
                "Corrupted or disguised files are not permitted."
            )

        # 6. Dimensional inspection
        width, height = cls.parse_dimensions(declared_mime, image_bytes)
        if width > 0 and height > 0:
            if (
                width > settings.MAX_IMAGE_DIMENSION
                or height > settings.MAX_IMAGE_DIMENSION
            ):
                raise ImageValidationError(
                    f"Image dimensions ({width}x{height}) exceed maximum allowed dimension of "
                    f"{settings.MAX_IMAGE_DIMENSION}px."
                )

        normalized_data_url = f"data:{declared_mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

        return ValidatedImage(
            mime_type=declared_mime,
            data_url=normalized_data_url,
            size_bytes=size_bytes,
            width=width,
            height=height,
        )
