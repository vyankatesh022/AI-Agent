"""SQLAlchemy database models for Users, Conversations, Messages, and Documents."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """User entity storing credentials and account creation timestamp."""

    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    documents = relationship(
        "Document", back_populates="owner", cascade="all, delete-orphan"
    )
    chunks = relationship(
        "DocumentChunkModel",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Conversation(Base):
    """Conversation entity owned by a user."""

    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """Message entity belonging to a conversation."""

    __tablename__ = "messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="messages")


class Document(Base):
    """Document metadata entity representing an uploaded user file."""

    __tablename__ = "documents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), default="application/pdf", nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    status = Column(
        String(50), default="pending", nullable=False
    )  # pending, processing, ready, failed
    page_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    processing_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner = relationship("User", back_populates="documents")
    chunks = relationship(
        "DocumentChunkModel",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunkModel(Base):
    """Authoritative chunk text and full-text search vector stored in PostgreSQL."""

    __tablename__ = "document_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    search_vector = Column(TSVECTOR, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    document = relationship("Document", back_populates="chunks")
    user = relationship("User", back_populates="chunks")

    __table_args__ = (
        Index(
            "ix_document_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index("ix_document_chunks_user_doc", "user_id", "document_id"),
    )
