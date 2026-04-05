"""Request payload size limit middleware to defend against memory exhaustion and DoS."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

logger = logging.getLogger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces upper bounds on incoming request payloads."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        max_bytes = settings.MAX_REQUEST_SIZE_MB * 1024 * 1024

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > max_bytes:
                    logger.warning(
                        "Payload too large: length=%d bytes max=%d bytes route=%s",
                        length,
                        max_bytes,
                        request.url.path,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": (
                                f"Payload exceeds maximum allowed size of "
                                f"{settings.MAX_REQUEST_SIZE_MB}MB."
                            ),
                            "error_code": "VALIDATION_ERROR",
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)
