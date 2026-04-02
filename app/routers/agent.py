"""Agent router exposing the LangGraph multi-model conversational endpoint."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.graph import build_agent_graph
from app.agent.state import AgentState
from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.llm.factory import LLMFactory
from app.models import Conversation, Message, User
from app.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    ModelsResponse,
    ProviderModels,
)
from app.tools.base import ToolRegistry
from app.tools.safe_database import SafeDatabaseTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="List available LLM providers and models",
)
async def list_models(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelsResponse:
    """Return backend-approved LLM providers and models."""
    default_model = (
        settings.GEMINI_MODEL
        if settings.LLM_PROVIDER == "gemini"
        else settings.OPENAI_MODEL
    )
    return ModelsResponse(
        default_provider=settings.LLM_PROVIDER,
        default_model=default_model,
        providers={
            "gemini": ProviderModels(
                name="Google Gemini",
                models=sorted(LLMFactory.ALLOWED_MODELS.get("gemini", set())),
            ),
            "openai": ProviderModels(
                name="OpenAI",
                models=sorted(LLMFactory.ALLOWED_MODELS.get("openai", set())),
            ),
        },
    )


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    summary="Send a message to the LangGraph AI Agent",
)
async def chat(
    payload: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentChatResponse:
    """Execute user query through the LangGraph agent with strict tenant isolation."""
    # 1. Verify conversation exists and belongs exclusively to the caller
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == payload.conversation_id)
        .first()
    )
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # 2. Validate optional request-level provider and model against allowlists
    target_provider = (payload.provider or settings.LLM_PROVIDER).strip().lower()
    if target_provider not in LLMFactory.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported provider '{payload.provider}'. "
                f"Allowed: {sorted(LLMFactory.SUPPORTED_PROVIDERS)}"
            ),
        )

    if payload.model:
        allowed_models = LLMFactory.ALLOWED_MODELS.get(target_provider, set())
        if payload.model not in allowed_models:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported model '{payload.model}' for provider "
                    f"'{target_provider}'. Allowed: {sorted(allowed_models)}"
                ),
            )

    # 3. Persist user's message before invoking agent
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.message.strip(),
    )
    db.add(user_msg)
    db.commit()

    # 4. Resolve LLM provider through abstraction factory
    try:
        llm_provider = LLMFactory.create_provider(
            provider_name=target_provider,
            model_name=payload.model,
            settings=settings,
        )
    except ValueError as exc:
        logger.error("LLM Provider initialization error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Language model provider is not properly configured.",
        ) from exc

    # 5. Initialize tool registry with authorized tools
    tool_registry = ToolRegistry()
    tool_registry.register(SafeDatabaseTool())

    # 6. Build and invoke LangGraph state graph
    graph = build_agent_graph(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        db=db,
        max_retries=settings.LLM_MAX_RETRIES,
    )

    initial_state: AgentState = {
        "messages": [{"role": "user", "content": payload.message.strip()}],
        "user_id": str(current_user.id),
        "conversation_id": str(conversation.id),
        "intent": "unknown",
        "selected_provider": llm_provider.provider_name,
        "selected_model": llm_provider.model_name,
        "tool_name": None,
        "tool_operation": None,
        "tool_result": None,
        "error": None,
        "retry_count": 0,
        "final_response": None,
        "citations": None,
        "sources": None,
    }

    try:
        result = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error("LangGraph agent execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent workflow encountered an error processing the request.",
        ) from exc

    final_text = (
        result.get("final_response")
        or "I was unable to complete the request. Please try again."
    )

    # 7. Persist assistant response
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=final_text,
    )
    db.add(assistant_msg)
    db.commit()

    # Safe log of operational metadata
    logger.info(
        "Agent completed request: user=%s conv=%s provider=%s intent=%s retries=%d",
        current_user.id,
        conversation.id,
        llm_provider.provider_name,
        result.get("intent", "general_chat"),
        result.get("retry_count", 0),
    )

    raw_citations = result.get("citations")
    serialized_citations = (
        [c.to_dict() if hasattr(c, "to_dict") else c for c in raw_citations]
        if raw_citations
        else None
    )
    raw_sources = result.get("sources")
    serialized_sources = (
        [s.to_dict() if hasattr(s, "to_dict") else s for s in raw_sources]
        if raw_sources
        else None
    )

    return AgentChatResponse(
        conversation_id=conversation.id,
        message=final_text,
        role="assistant",
        intent=result.get("intent", "general_chat"),
        provider=llm_provider.provider_name,
        model=llm_provider.model_name,
        citations=serialized_citations,
        sources=serialized_sources,
    )
