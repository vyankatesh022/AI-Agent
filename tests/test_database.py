"""Automated tests for direct database operations, models, and constraints."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Conversation, Message, User
from app.security import hash_password


def test_user_creation_and_retrieval(db_session: Session) -> None:
    """Verify creating and querying a User in PostgreSQL."""
    user = User(
        email="db_test_user@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()

    retrieved = (
        db_session.query(User)
        .filter(User.email == "db_test_user@example.com")
        .first()
    )
    assert retrieved is not None
    assert retrieved.id == user.id
    assert retrieved.email == "db_test_user@example.com"
    assert retrieved.created_at is not None


def test_conversation_and_message_relationship(db_session: Session) -> None:
    """Verify Conversation and Message models and their relationship bindings."""
    user = User(
        email="rel_user@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()

    conv = Conversation(
        title="Architecture Discussion",
        user_id=user.id,
    )
    db_session.add(conv)
    db_session.commit()

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content="Hello AI Agent!",
    )
    db_session.add(msg)
    db_session.commit()

    # Query through relationships
    loaded_conv = (
        db_session.query(Conversation)
        .filter(Conversation.id == conv.id)
        .first()
    )
    assert loaded_conv is not None
    assert loaded_conv.user.email == "rel_user@example.com"
    assert len(loaded_conv.messages) == 1
    assert loaded_conv.messages[0].content == "Hello AI Agent!"


def test_cascade_delete_behavior(db_session: Session) -> None:
    """Verify deleting a user cascades to their conversations and messages."""
    user = User(
        email="cascade_user@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title="Temporary Conversation", user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content="I will be deleted when user is deleted.",
    )
    db_session.add(msg)
    db_session.commit()

    conv_id = conv.id
    msg_id = msg.id

    # Delete parent user
    db_session.delete(user)
    db_session.commit()

    # Verify conversation and message no longer exist
    assert (
        db_session.query(Conversation)
        .filter(Conversation.id == conv_id)
        .first()
        is None
    )
    assert (
        db_session.query(Message).filter(Message.id == msg_id).first() is None
    )


def test_unique_email_constraint_enforced(db_session: Session) -> None:
    """Verify that PostgreSQL enforces uniqueness on the email column."""
    user1 = User(
        email="unique_check@example.com",
        password_hash=hash_password("pw1"),
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        email="unique_check@example.com",
        password_hash=hash_password("pw2"),
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_transaction_rollback_on_error(db_session: Session) -> None:
    """Verify that a rolled back transaction does not persist uncommitted changes."""
    user = User(
        email="rollback_user@example.com",
        password_hash=hash_password("pw1"),
    )
    db_session.add(user)
    # Rollback before committing
    db_session.rollback()

    retrieved = (
        db_session.query(User)
        .filter(User.email == "rollback_user@example.com")
        .first()
    )
    assert retrieved is None
