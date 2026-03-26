"""Safe database tool exposing strictly scoped, user-isolated operations."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Conversation, Message, User
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SafeDatabaseTool(BaseTool):
    """Tool allowing safe, read-only queries bounded strictly to the caller's data.

    STRICT SECURITY CONTROLS:
    - Never accepts or executes raw SQL from the model.
    - Always requires the authenticated user_id from application context.
    - User A can never query or inspect User B's records.
    """

    ALLOWED_OPERATIONS = {
        "get_current_user_profile",
        "get_user_conversations",
        "get_conversation_summary",
    }

    @property
    def name(self) -> str:
        return "safe_database"

    @property
    def description(self) -> str:
        return (
            "Access user's account details and conversation metadata. "
            "Supported operations: 'get_current_user_profile', "
            "'get_user_conversations', 'get_conversation_summary'."
        )

    async def execute(
        self,
        user_id: uuid.UUID,
        operation: str = "get_current_user_profile",
        conversation_id: str | None = None,
        db_session: Session | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a whitelisted database operation scoped to user_id."""
        if operation not in self.ALLOWED_OPERATIONS:
            raise ValueError(
                f"Unauthorized database operation '{operation}'. "
                f"Allowed operations: {', '.join(sorted(self.ALLOWED_OPERATIONS))}"
            )

        # Allow passing an existing session (useful for test isolation) or create one
        session = db_session if db_session is not None else SessionLocal()
        should_close = db_session is None

        try:
            if operation == "get_current_user_profile":
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    return {"error": "User not found"}
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "created_at": user.created_at.isoformat(),
                }

            if operation == "get_user_conversations":
                conversations = (
                    session.query(Conversation)
                    .filter(Conversation.user_id == user_id)
                    .order_by(Conversation.created_at.desc())
                    .limit(20)
                    .all()
                )
                return {
                    "count": len(conversations),
                    "conversations": [
                        {
                            "id": str(c.id),
                            "title": c.title,
                            "created_at": c.created_at.isoformat(),
                        }
                        for c in conversations
                    ],
                }

            if operation == "get_conversation_summary":
                if not conversation_id:
                    return {"error": "conversation_id is required for summary"}

                try:
                    target_uuid = uuid.UUID(str(conversation_id))
                except ValueError:
                    return {"error": "Invalid conversation_id UUID format"}

                # Enforce ownership: must match target conversation AND user_id
                conv = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == target_uuid,
                        Conversation.user_id == user_id,
                    )
                    .first()
                )
                if not conv:
                    return {"error": "Conversation not found or access denied"}

                messages = (
                    session.query(Message)
                    .filter(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc())
                    .limit(5)
                    .all()
                )

                return {
                    "conversation_id": str(conv.id),
                    "title": conv.title,
                    "total_messages": len(conv.messages),
                    "recent_messages": [
                        {"role": m.role, "content": m.content[:100]}
                        for m in reversed(messages)
                    ],
                }

            return {"error": "Unsupported operation"}

        finally:
            if should_close:
                session.close()
