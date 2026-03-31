"""Pydantic schemas for request validation and response serialization."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    """Payload schema for user registration."""

    email: EmailStr = Field(description="Valid user email address")
    password: str = Field(
        min_length=8,
        description="Password with minimum 8 characters",
    )


class UserLogin(BaseModel):
    """Payload schema for user login authentication."""

    email: EmailStr = Field(description="Registered user email address")
    password: str = Field(description="User password")


class UserResponse(BaseModel):
    """Safe user profile response schema (never exposes password or hashes)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    """Authentication token response schema."""

    access_token: str = Field(description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme")


class ConversationCreate(BaseModel):
    """Payload schema for initiating a new conversation."""

    title: str = Field(
        min_length=1,
        max_length=255,
        description="Human-readable title of the conversation",
    )


class ConversationResponse(BaseModel):
    """Conversation metadata response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    created_at: datetime


class MessageResponse(BaseModel):
    """Message response schema for conversation history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime


class AgentChatRequest(BaseModel):
    """Request payload for invoking the LangGraph agent."""

    conversation_id: UUID = Field(
        description="Target conversation UUID belonging to the authenticated user",
    )
    message: str = Field(
        min_length=1,
        description="User text prompt or query",
    )
    provider: str | None = Field(
        default=None,
        description="Optional provider override ('gemini' or 'openai')",
    )
    model: str | None = Field(
        default=None,
        description="Optional model override from the approved model allowlist",
    )


class AgentChatResponse(BaseModel):
    """Response payload returned by the LangGraph agent."""

    conversation_id: UUID
    message: str
    role: str = "assistant"
    intent: str
    provider: str
    model: str
    citations: list[dict[str, Any]] | None = None
    sources: list[dict[str, Any]] | None = None


class DocumentResponse(BaseModel):
    """Document metadata response representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    file_size: int
    content_type: str
    status: str
    page_count: int
    chunk_count: int
    processing_error: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """List response for documents owned by user."""

    documents: list[DocumentResponse]
    total: int


class RAGQueryRequest(BaseModel):
    """Direct RAG query payload."""

    query: str = Field(
        min_length=1,
        max_length=2000,
        description="Question to answer using indexed documents",
    )
    top_k: int | None = Field(
        default=None, ge=1, le=20, description="Optional chunk retrieval count"
    )
    provider: str | None = Field(
        default=None, description="Optional LLM provider override"
    )
    model: str | None = Field(default=None, description="Optional LLM model override")


class RAGQueryResponse(BaseModel):
    """Grounded RAG query response with citations."""

    query: str
    response: str
    citations: list[dict[str, Any]]
    sources: list[dict[str, Any]] | None = None
    retrieved_count: int
    retrieval_mode: str = "hybrid"
    provider: str
    model: str
