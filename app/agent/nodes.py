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
from app.memory.service import ConversationMemoryService
from app.rag.pipeline import RAGPipeline
from app.security.tool_policy import ToolPolicyEnforcer
from app.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


async def load_context_node(state: AgentState, db: Session) -> dict[str, Any]:
    """Load bounded conversation history using ConversationMemoryService."""
    conv_id = state.get("conversation_id")
    user_id_str = state.get("user_id")
    messages = list(state.get("messages", []))

    if conv_id and user_id_str:
        try:
            conv_uuid = uuid.UUID(conv_id)
            user_uuid = uuid.UUID(user_id_str)
            memory_service = ConversationMemoryService()
            ctx = memory_service.load_context(
                db=db,
                user_id=user_uuid,
                conversation_id=conv_uuid,
            )
            history = ctx.to_message_dicts()
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
    # Multimodal image queries are handled directly by the vision model in general_chat
    if state.get("image"):
        return {"intent": "general_chat"}

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

    doc_keywords = [
        "document",
        "documents",
        "pdf",
        "pdfs",
        "uploaded file",
        "uploaded files",
        "policy",
        "policies",
        "report",
        "what does the doc say",
        "in my document",
        "in the file",
    ]
    if any(k in lower_query for k in doc_keywords):
        return {"intent": "document_search"}

    try:
        classification_prompt = [
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": f"Query to classify:\n{user_query}"},
        ]
        raw_intent = await llm_provider.generate_response(
            messages=classification_prompt,
        )
        normalized = raw_intent.strip().lower().replace('"', "").replace("'", "")

        if "database" in normalized:
            tool_op = "get_current_user_profile"
            if "conversation" in lower_query:
                tool_op = "get_user_conversations"
            return {
                "intent": "database_query",
                "tool_name": "safe_database",
                "tool_operation": tool_op,
            }
        if "document" in normalized:
            return {"intent": "document_search"}
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
    messages = list(state.get("messages", []))
    image_url = state.get("image")

    # If an image was attached in this turn, attach it to the latest user message
    if image_url and messages:
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "user":
                last_msg = dict(messages[idx])
                last_msg["image"] = image_url
                messages[idx] = last_msg
                break

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
    tool_policy: ToolPolicyEnforcer | None = None,
) -> dict[str, Any]:
    """Execute authorized tool under caller's tenant boundary with policy enforcement."""
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

        enforcer = tool_policy or ToolPolicyEnforcer()
        validated_kwargs = enforcer.validate_and_authorize(
            tool_name=tool_name,
            user_id=user_uuid,
            operation=operation,
            conversation_id=conversation_id,
            db_session=db,
        )

        result = await tool_registry.execute_tool(
            tool_name=tool_name,
            **validated_kwargs,
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
        return {"final_response": f"Here is the requested information:\n{tool_result}"}


async def rag_node(
    state: AgentState,
    llm_provider: BaseLLMProvider,
    retriever: Any | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Execute grounded RAG workflow for document search queries."""
    user_id_str = state.get("user_id")
    if not user_id_str:
        return {
            "final_response": "Missing user identification for document search.",
            "error": "Unauthenticated user in RAG node",
        }

    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    try:
        user_uuid = uuid.UUID(user_id_str)
        pipeline = RAGPipeline(retriever=retriever)
        rag_result = await pipeline.run(
            user_id=user_uuid,
            query=user_query,
            llm_provider=llm_provider,
            db=db,
        )
        citations_list = [
            c.to_dict() if hasattr(c, "to_dict") else c for c in rag_result.citations
        ]
        return {
            "final_response": rag_result.response,
            "citations": citations_list,
            "sources": [s.to_dict() for s in rag_result.sources],
            "error": None,
        }
    except Exception as exc:
        logger.error("RAG node execution error: %s", exc)
        return {
            "final_response": (
                "An error occurred while retrieving or searching through "
                "your documents. Please try again."
            ),
            "error": str(exc),
        }
