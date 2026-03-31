"""Data models for bounded conversation memory and history budgets."""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class MemoryMessage:
    """Individual conversation message representation within memory context."""

    role: str
    content: str
    created_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ConversationContext:
    """Bounded conversation memory context ready for agent prompting."""

    messages: list[MemoryMessage]
    total_characters: int
    truncated: bool = False

    def to_message_dicts(self) -> list[dict[str, str]]:
        return [m.to_dict() for m in self.messages]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
