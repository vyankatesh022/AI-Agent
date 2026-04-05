"""Cryptographic utilities and security hardening abstractions."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.security.errors import (
    AppSecurityException,
    ErrorCode,
    PromptInjectionError,
    RateLimitExceededError,
    ToolAuthorizationError,
)
from app.security.headers import SecurityHeadersMiddleware
from app.security.prompt_guard import PromptGuard
from app.security.rate_limit import (
    RateLimitChecker,
    SlidingWindowRateLimiter,
    get_client_ip,
    limiter,
)
from app.security.request_size import RequestSizeLimitMiddleware
from app.security.tool_policy import ToolPolicyEnforcer

logger = logging.getLogger(__name__)

# Argon2 Password Hasher using recommended parameters
_password_hasher = PasswordHasher()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception as exc:
        logger.warning("Unexpected error during password verification: %s", exc)
        return False


def create_access_token(
    subject: str,
    secret_key: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT access token for an authenticated user.

    The payload only contains the minimal necessary identity information:
    - sub: subject (user UUID)
    - exp: expiration timestamp
    - iat: issued-at timestamp
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta else timedelta(hours=24))

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises:
        jwt.PyJWTError: If the token is invalid, expired, or malformed.
    """
    return jwt.decode(token, secret_key, algorithms=[ALGORITHM])


__all__ = [
    "ALGORITHM",
    "AppSecurityException",
    "ErrorCode",
    "PromptGuard",
    "PromptInjectionError",
    "RateLimitChecker",
    "RateLimitExceededError",
    "RequestSizeLimitMiddleware",
    "SecurityHeadersMiddleware",
    "SlidingWindowRateLimiter",
    "ToolAuthorizationError",
    "ToolPolicyEnforcer",
    "create_access_token",
    "decode_access_token",
    "get_client_ip",
    "hash_password",
    "limiter",
    "verify_password",
]
