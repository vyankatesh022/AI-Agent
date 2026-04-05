"""Standardized error classifications and security exception models."""

from enum import Enum


class ErrorCode(str, Enum):
    """High-level security and operational error classification codes."""

    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    PROMPT_INJECTION_ERROR = "PROMPT_INJECTION_ERROR"
    LLM_ERROR = "LLM_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    DOCUMENT_ERROR = "DOCUMENT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppSecurityException(Exception):
    """Base exception for application security violations."""

    def __init__(
        self,
        detail: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 400,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code


class PromptInjectionError(AppSecurityException):
    """Raised when an adversarial instruction or prompt injection signal is detected."""

    def __init__(
        self, detail: str = "Request contains disallowed adversarial instructions."
    ) -> None:
        super().__init__(
            detail=detail,
            error_code=ErrorCode.PROMPT_INJECTION_ERROR,
            status_code=400,
        )


class ToolAuthorizationError(AppSecurityException):
    """Raised when an unapproved tool, invalid arguments, or excessive tool calls occur."""

    def __init__(self, detail: str = "Tool invocation is unauthorized.") -> None:
        super().__init__(
            detail=detail,
            error_code=ErrorCode.TOOL_ERROR,
            status_code=403,
        )


class RateLimitExceededError(AppSecurityException):
    """Raised when an IP or user exceeds allowable request frequencies."""

    def __init__(
        self,
        retry_after_seconds: int = 60,
        detail: str | None = None,
    ) -> None:
        message = (
            detail
            if detail
            else f"Rate limit exceeded. Please retry in {retry_after_seconds} seconds."
        )
        super().__init__(
            detail=message,
            error_code=ErrorCode.RATE_LIMIT_ERROR,
            status_code=429,
        )
        self.retry_after_seconds = retry_after_seconds
