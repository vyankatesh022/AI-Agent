"""Request telemetry and LLM token accounting data models."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMUsage:
    """Normalized token accounting model across LLM providers."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "LLMUsage") -> "LLMUsage":
        """Accumulate token counts."""
        return LLMUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class RequestTelemetry:
    """End-to-end telemetry recorded during request processing."""

    request_id: str
    user_id: str | None = None
    session_id: str | None = None
    endpoint: str = ""
    duration_ms: float = 0.0
    intent: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: LLMUsage | None = None
    retry_count: int = 0
    tool_calls: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    error_type: str | None = None
    has_image: bool = False
    image_size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "endpoint": self.endpoint,
            "duration_ms": round(self.duration_ms, 2),
            "intent": self.intent,
            "provider": self.provider,
            "model": self.model,
            "usage": self.usage.to_dict() if self.usage else None,
            "retry_count": self.retry_count,
            "tool_calls": self.tool_calls,
            "retrieval_count": self.retrieval_count,
            "error_type": self.error_type,
            "has_image": self.has_image,
            "image_size_bytes": self.image_size_bytes,
        }


current_telemetry: ContextVar[RequestTelemetry | None] = ContextVar(
    "current_telemetry", default=None
)
current_request_id: ContextVar[str | None] = ContextVar(
    "current_request_id", default=None
)


def get_current_telemetry() -> RequestTelemetry | None:
    """Retrieve active RequestTelemetry object from context."""
    return current_telemetry.get()


def set_current_telemetry(telemetry: RequestTelemetry | None) -> None:
    """Set active RequestTelemetry object in context."""
    current_telemetry.set(telemetry)


def get_current_request_id() -> str:
    """Retrieve active correlation request ID from context, or default placeholder."""
    return current_request_id.get() or "no-req-id"
