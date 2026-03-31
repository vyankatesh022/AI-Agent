"""Conversation memory service enforcing database-side limits and tenant boundaries."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.memory.models import ConversationContext, MemoryMessage
from app.models import Conversation, Message

logger = logging.getLogger(__name__)


class ConversationMemoryService:
    """Manages bounded conversation history loading and memory budgeting."""

    def __init__(
        self,
        max_messages: int | None = None,
        max_chars: int | None = None,
    ) -> None:
        settings = get_settings()
        self.max_messages = (
            max_messages
            if max_messages is not None
            else settings.MAX_CONVERSATION_MESSAGES
        )
        self.max_chars = (
            max_chars if max_chars is not None else settings.MAX_CONTEXT_TOKENS
        )

    def load_context(
        self,
        db: Session,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int | None = None,
        char_budget: int | None = None,
    ) -> ConversationContext:
        """Fetch recent conversation turns bounded by message count and character budget.

        Security guarantee:
        - Query joins Conversation and enforces Conversation.user_id == user_id in SQL.
        - User A can NEVER load or infer User B's conversation history.

        Args:
            db: Database session.
            user_id: Authenticated user ID.
            conversation_id: Conversation thread identifier.
            limit: Optional override for max messages.
            char_budget: Optional override for max character count.

        Returns:
            ConversationContext containing bounded chronological messages.
        """
        max_msgs = limit or self.max_messages
        budget = char_budget or self.max_chars

        # Efficient database-side limit and ownership check
        recent_rows = (
            db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(Message.created_at.desc())
            .limit(max_msgs)
            .all()
        )

        if not recent_rows:
            return ConversationContext(
                messages=[],
                total_characters=0,
                truncated=False,
            )

        # Restore chronological order (oldest to newest among the recent window)
        chronological_rows = list(reversed(recent_rows))

        # Apply character budget (trim from oldest if budget is exceeded)
        messages: list[MemoryMessage] = []
        current_len = 0
        truncated = False

        # Work backwards from the newest to ensure most recent messages are kept
        kept_rows: list[Message] = []
        for msg in reversed(chronological_rows):
            msg_len = len(msg.content)
            if current_len + msg_len > budget and kept_rows:
                truncated = True
                break
            kept_rows.append(msg)
            current_len += msg_len

        # Re-sort kept rows to chronological order
        for msg in reversed(kept_rows):
            messages.append(
                MemoryMessage(
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at,
                )
            )

        logger.debug(
            "Loaded memory context: conv=%s user=%s messages=%d chars=%d truncated=%s",
            conversation_id,
            user_id,
            len(messages),
            current_len,
            truncated,
        )

        return ConversationContext(
            messages=messages,
            total_characters=current_len,
            truncated=truncated,
        )
