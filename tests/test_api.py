"""Automated tests for FastAPI endpoints and core configuration."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Ensure required environment variables exist before importing application settings
os.environ.setdefault("APP_NAME", "AI Agent API")
os.environ.setdefault("APP_VERSION", "0.1.0")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-at-least-32-characters-long-123456"
)
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from app.config import Settings, get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Fixture providing a FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


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
        Settings(SECRET_KEY="short-secret")


def test_settings_loaded_from_env() -> None:
    """Verify that settings correctly reflect environment values."""
    settings = get_settings()
    assert settings.APP_NAME == "AI Agent API"
    assert settings.APP_VERSION == "0.1.0"
    assert len(settings.SECRET_KEY) >= 32
