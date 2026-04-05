"""Memory-bounded sliding-window rate limiter for application endpoints."""

import logging
import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.security.errors import ErrorCode

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """In-memory sliding-window rate limiter with deterministic memory bounds.

    Features:
    - Sliding window precision using monotonic clock timestamps.
    - Automatic eviction of stale window entries.
    - Max tracked keys cap to prevent memory exhaustion attacks.
    """

    def __init__(self, max_keys: int = 10000) -> None:
        self.max_keys = max_keys
        self._records: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """Check if request for key is allowed under configured window.

        Args:
            key: Rate limit bucket key (e.g., 'login:192.168.1.1' or 'agent:user_uuid').
            limit: Maximum allowed requests within window_seconds.
            window_seconds: Window duration in seconds (default: 60).

        Returns:
            Tuple of (is_allowed: bool, retry_after_seconds: int).
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            # Memory safeguard: prune dictionary if approaching max capacity
            if len(self._records) >= self.max_keys and key not in self._records:
                self._prune_stale_records(cutoff)
                if len(self._records) >= self.max_keys:
                    # Pop oldest key to prevent unbounded growth
                    first_key = next(iter(self._records))
                    del self._records[first_key]

            timestamps = self._records.setdefault(key, deque())

            # Evict timestamps older than window cutoff
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                # Earliest timestamp indicates when next token will become available
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after

            # Record current timestamp
            timestamps.append(now)
            return True, 0

    def _prune_stale_records(self, cutoff: float) -> None:
        """Remove empty key buckets whose timestamps have completely expired."""
        stale_keys = [
            k
            for k, timestamps in self._records.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for k in stale_keys:
            del self._records[k]

    def clear(self) -> None:
        """Clear all rate limit state (used for testing)."""
        with self._lock:
            self._records.clear()


# Global in-memory rate limiter singleton
limiter = SlidingWindowRateLimiter()


def get_client_ip(request: Request) -> str:
    """Safely extract client IP from forward headers or direct socket."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Use first proxy client IP in list
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class RateLimitChecker:
    """FastAPI Dependency enforcing rate limits per endpoint."""

    def __init__(
        self,
        endpoint_name: str,
        limit_getter: str,
        key_type: str = "ip",  # 'ip' or 'user'
    ) -> None:
        self.endpoint_name = endpoint_name
        self.limit_getter = limit_getter
        self.key_type = key_type

    async def __call__(
        self,
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit = getattr(settings, self.limit_getter, 60)

        if self.key_type == "user":
            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header[7:].strip()
                    try:
                        from app.security import decode_access_token

                        payload = decode_access_token(token, settings.SECRET_KEY)
                        user_id = payload.get("sub")
                    except Exception:
                        user_id = None

            if user_id:
                bucket_key = f"{self.endpoint_name}:{user_id}"
            else:
                client_ip = get_client_ip(request)
                bucket_key = f"{self.endpoint_name}:{client_ip}"
        else:
            client_ip = get_client_ip(request)
            bucket_key = f"{self.endpoint_name}:{client_ip}"

        allowed, retry_after = limiter.is_allowed(
            key=bucket_key,
            limit=limit,
            window_seconds=60,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded: endpoint=%s key=%s limit=%d/min retry_after=%ds",
                self.endpoint_name,
                bucket_key,
                limit,
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-Error-Code": ErrorCode.RATE_LIMIT_ERROR.value,
                },
            )
