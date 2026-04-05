"""Observability middleware for correlation tracing, monotonic timing, and metrics."""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability.telemetry import (
    RequestTelemetry,
    current_request_id,
    current_telemetry,
)

logger = logging.getLogger(__name__)

# Valid request ID format: 1-64 chars of alphanumeric and hyphen
REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Correlation tracing, latency measurement, and request telemetry middleware."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 1. Resolve or generate correlation request ID
        header_req_id = request.headers.get("X-Request-ID")
        if header_req_id and REQUEST_ID_REGEX.match(header_req_id):
            request_id = header_req_id
        else:
            request_id = str(uuid.uuid4())

        # Set request-scoped state and ContextVars
        request.state.request_id = request_id
        req_token = current_request_id.set(request_id)

        telemetry = RequestTelemetry(
            request_id=request_id,
            endpoint=request.url.path,
        )
        request.state.telemetry = telemetry
        telem_token = current_telemetry.set(telemetry)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            telemetry.duration_ms = duration_ms
            logger.error(
                "Request failed with unhandled exception: %s %s duration=%.2fms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        finally:
            current_request_id.reset(req_token)
            current_telemetry.reset(telem_token)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        telemetry.duration_ms = duration_ms

        # Inject telemetry response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"

        logger.info(
            "Request finished: %s %s status=%d duration=%.2fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response
