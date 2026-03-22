"""Application logging configuration.

Designed for production reliability and future observability:
- Provides structured context fields (request_id, user_id, session_id).
- Ready for future metric and tracing extensions (latencies, token counts, tool calls).
- STRICT SECURITY RULE: Never log credentials, API keys, bearer tokens, passwords,
  or private customer document contents.
"""

import logging
import sys


class ContextFilter(logging.Filter):
    """Filter that ensures standard contextual attributes exist on every LogRecord.

    Prepares the logging infrastructure for future sessions (Session 6 observability):
    - request_id: Unique correlation ID for tracing distributed requests.
    - user_id: Authenticated user identifier (added in Session 2).
    - session_id: Conversation session identifier (added in Session 3-5).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "user_id"):
            record.user_id = "-"
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """Configure standard application logging for stdout streaming.

    Args:
        log_level: Desired log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_format = (
        "%(asctime)s | %(levelname)-8s | [%(name)s] "
        "[req=%(request_id)s user=%(user_id)s session=%(session_id)s] "
        "- %(message)s"
    )

    formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers to prevent duplicate lines on reload
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Keep third-party server loggers aligned with the configured level
    logging.getLogger("uvicorn").setLevel(numeric_level)
    logging.getLogger("uvicorn.access").setLevel(numeric_level)
