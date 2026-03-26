"""Execution nodes for the LangGraph state machine."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agent.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    SYSTEM_PROMPT,
    TOOL_SYNTHESIS_PROMPT,
)
from app.agent.state import AgentState
from app.llm.base import BaseLLMProvider
from app.models import Message
from app.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


async def load_context_node(state: AgentState, db: Session) -> dict[str, Any]:
    """Load conversation history from PostgreSQL to provide context."""
    conv_id = state.get("conversation_id")
    messages = list(state.get("messages", []))

    if conv_id:
        try:
            conv_uuid = uuid.UUID(conv_id)
            past_messages = (
                db.query(Message)
                .filter(Message.conversation_id == conv_uuid)
                .order_by(Message.created_at.asc())
                .limit(10)
                .all()
            )
            history = [
                {"role": m.role, "content": m.content} for m in past_messages
            ]
            if (
                messages
                and history
                and history[-1]["content"] == messages[-1]["content"]
            ):
                messages = history
            else:
                messages = history + messages
        except Exception as exc:
            logger.warning("Error loading conversation history: %s", exc)

    return {"messages": messages}


async def classify_intent_node(
    state: AgentState,
    llm_provider: BaseLLMProvider,
) -> dict[str, Any]:
    """Classify the user query into 'general_chat' or 'database_query'."""
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    if not user_query:
        return {"intent": "general_chat"}

    lower_query = user_query.lower()
    db_keywords = [
        "my account",
        "my profile",
        "my conversations",
        "list my chats",
        "summary of this conversation",
    ]
    if any(k in lower_query for k in db_keywords):
        tool_op = "get_current_user_profile"
        if "conversation" in lower_query or "chats" in lower_query:
            tool_op = "get_user_conversations"
        return {
            "intent": "database_query",
            "tool_name": "safe_database",
            "tool_operation": tool_op,
        }

    try:
        classification_prompt = [
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": f"Query to classify:\n{user_query}"},
        ]
        raw_intent = await llm_provider.generate_response(
            messages=classification_prompt,
        )
        normalized = (
            raw_intent.strip().lower().replace('"', "").replace("'", "")
        )

        if "database" in normalized:
            tool_op = "get_current_user_profile"
            if "conversation" in lower_query:
                tool_op = "get_user_conversations"
            return {
                "intent": "database_query",
                "tool_name": "safe_database",
                "tool_operation": tool_op,
            }
        return {"intent": "general_chat"}

    except Exception as exc:
        logger.warning(
            "Intent classification failed, falling back to general_chat: %s",
            exc,
        )
        return {"intent": "general_chat", "error": str(exc)}


async def normal_llm_node(
    state: AgentState,
    llm_provider: BaseLLMProvider,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Execute standard LLM generation with bounded retry handling."""
    retry_count = state.get("retry_count", 0)
    messages = state.get("messages", [])

    while retry_count <= max_retries:
        try:
            response_text = await llm_provider.generate_response(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
            )
            return {
                "final_response": response_text,
                "retry_count": retry_count,
                "error": None,
            }
        except Exception as exc:
            retry_count += 1
            logger.warning(
                "Transient LLM failure on attempt %d: %s",
                retry_count,
                exc,
            )
            if retry_count > max_retries:
                logger.error("LLM retries exhausted: %s", exc)
                return {
                    "final_response": (
                        "I am experiencing temporary connection difficulties "
                        "with the language model. Please try again shortly."
                    ),
                    "retry_count": retry_count,
                    "error": str(exc),
                }

    return {
        "final_response": "Service temporarily unavailable.",
        "retry_count": retry_count,
        "error": "Exceeded retry threshold",
    }


async def execute_tool_node(
    state: AgentState,
    tool_registry: ToolRegistry,
    db: Session,
) -> dict[str, Any]:
    """Execute authorized tool under caller's tenant boundary."""
    tool_name = state.get("tool_name", "safe_database")
    user_id_str = state.get("user_id")

    if not user_id_str:
        return {
            "tool_result": {"error": "Missing authenticated user context"},
            "error": "Unauthenticated tool call",
        }

    try:
        user_uuid = uuid.UUID(user_id_str)
        operation = state.get("tool_operation") or "get_current_user_profile"
        conversation_id = state.get("conversation_id")

        result = await tool_registry.execute_tool(
            tool_name=tool_name,
            user_id=user_uuid,
            operation=operation,
            conversation_id=conversation_id,
            db_session=db,
        )
        return {"tool_result": result, "error": None}
    except Exception as exc:
        logger.error("Tool execution failed: %s", exc)
        return {
            "tool_result": {"error": str(exc)},
            "error": str(exc),
        }


async def synthesize_tool_response_node(
    state: AgentState,
    llm_provider: BaseLLMProvider,
) -> dict[str, Any]:
    """Synthesize structured tool output into a conversational response."""
    tool_result = state.get("tool_result", {})

    prompt_content = TOOL_SYNTHESIS_PROMPT.format(tool_result=tool_result)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_content},
    ]

    try:
        summary = await llm_provider.generate_response(messages=messages)
        return {"final_response": summary}
    except Exception as exc:
        logger.warning(
            "Tool synthesis LLM call failed, returning raw formatting: %s", exc
        )
        return {
            "final_response": f"Here is the requested information:\n{tool_result}"
        }
