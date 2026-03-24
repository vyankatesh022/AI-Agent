"""Automated tests for FastAPI endpoints and core configuration."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_health_endpoint_success(client: TestClient) -> None:
    """Verify GET /health returns 200 and matches the expected contract."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "AI Agent API"
    assert data["version"] == "0.1.0"


def test_settings_caching() -> None:
    """Verify get_settings returns the same cached instance across invocations."""
    settings_one = get_settings()
    settings_two = get_settings()
    assert settings_one is settings_two


def test_secret_key_minimum_length_enforcement() -> None:
    """Verify that a SECRET_KEY shorter than 32 characters raises a validation error."""
    with pytest.raises(ValidationError):
        Settings(
            SECRET_KEY="short-secret",
            DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/test",
        )


def test_database_url_required() -> None:
    """Verify that DATABASE_URL is required and raises validation error when missing."""
    with pytest.raises(ValidationError):
        Settings(
            SECRET_KEY="a" * 32,
            DATABASE_URL="",  # or missing
        )


def test_settings_loaded_from_env() -> None:
    """Verify that settings correctly reflect environment values."""
    settings = get_settings()
    assert settings.APP_NAME == "AI Agent API"
    assert settings.APP_VERSION == "0.1.0"
    assert len(settings.SECRET_KEY) >= 32
    assert "postgresql" in settings.DATABASE_URL
