"""Structured logging, sensitive data scrubbing, and security event auditing."""

import json
import logging
import re
from typing import Any

from app.observability.telemetry import (
    current_request_id,
    get_current_telemetry,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.security.audit")


class SensitiveDataScrubber(logging.Filter):
    """Logging filter that redacts credentials, keys, and tokens from log output."""

    SCRUB_PATTERNS = [
        # Bearer tokens
        (re.compile(r"Bearer\s+[A-Za-z0-9\-_=.]+", re.IGNORECASE), "Bearer [REDACTED]"),
        # OpenAI API Keys
        (re.compile(r"sk-[A-Za-z0-9\-_]{20,}"), "sk-[REDACTED]"),
        # Google Gemini API Keys
        (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "AIza[REDACTED]"),
        # Passwords in JSON-like or key-value structures
        (
            re.compile(
                r'("password"|\'password\'|password)\s*[:=]\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            ),
            r'\1: "[REDACTED]"',
        ),
        # Raw JWT strings
        (
            re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
            "[JWT_REDACTED]",
        ),
        # Base64 Image Payload Data URLs
        (
            re.compile(
                r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+\/=\s]{50,}",
                re.IGNORECASE,
            ),
            "[IMAGE_DATA_REDACTED]",
        ),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.scrub_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.scrub_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.scrub_value(arg) for arg in record.args)

        return True

    @classmethod
    def scrub_text(cls, text: str) -> str:
        """Apply all redaction patterns to a string."""
        if not isinstance(text, str):
            return text
        scrubbed = text
        for pattern, replacement in cls.SCRUB_PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)
        return scrubbed

    @classmethod
    def scrub_value(cls, value: Any) -> Any:
        """Scrub a value recursively if needed."""
        if isinstance(value, str):
            return cls.scrub_text(value)
        return value


class ContextualLogFormatter(logging.Formatter):
    """Log formatter that automatically enriches log lines with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = current_request_id.get() or "-"
        telemetry = get_current_telemetry()
        user_id = telemetry.user_id if telemetry and telemetry.user_id else "-"

        record.req_context = f"[req={req_id} user={user_id}]"
        return super().format(record)


def log_security_event(
    event_type: str,
    severity: str = "WARNING",
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Emit an auditable security event in structured format."""
    req_id = request_id or current_request_id.get() or "no-req-id"
    if not user_id:
        telemetry = get_current_telemetry()
        user_id = telemetry.user_id if telemetry and telemetry.user_id else None

    payload = {
        "event_type": event_type,
        "severity": severity.upper(),
        "request_id": req_id,
        "user_id": user_id,
        "details": details or {},
    }

    message = f"SECURITY_EVENT: {json.dumps(payload)}"
    level = getattr(logging, severity.upper(), logging.WARNING)
    audit_logger.log(level, message)
