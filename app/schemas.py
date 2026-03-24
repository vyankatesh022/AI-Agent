"""Pydantic schemas for request validation and response serialization."""

from datetime import datetime
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
