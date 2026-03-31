"""Application configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = Field(
        default="AI Agent API",
        description="Name of the service",
    )
    APP_VERSION: str = Field(
        default="0.5.0",
        description="Semantic version of the application",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development, staging, or production",
    )
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Cryptographic secret key; must be at least 32 characters long",
    )
    DATABASE_URL: str = Field(
        ...,
        min_length=1,
        description="PostgreSQL database connection URL",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,
        description="Token expiration duration in minutes",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Application logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # LLM Multi-Model Provider Settings
    LLM_PROVIDER: str = Field(
        default="gemini",
        description="Default LLM provider: 'gemini' or 'openai'",
    )
    OPENAI_API_KEY: str | None = Field(
        default=None,
        description="OpenAI API secret key",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Configured default OpenAI model",
    )
    GOOGLE_API_KEY: str | None = Field(
        default=None,
        description="Google Gemini API secret key",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.0-flash",
        description="Configured default Gemini model",
    )
    LLM_TIMEOUT_SECONDS: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Timeout in seconds for external LLM API calls",
    )
    LLM_MAX_RETRIES: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts for transient LLM errors",
    )

    # Document & RAG Settings
    DOCUMENT_STORAGE_PATH: str = Field(
        default="data/documents",
        description="Filesystem directory for uploaded document storage",
    )
    FAISS_INDEX_PATH: str = Field(
        default="data/indexes",
        description="Filesystem directory for user-isolated FAISS indexes",
    )
    MAX_DOCUMENT_SIZE_MB: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum allowed uploaded PDF size in megabytes",
    )
    RAG_CHUNK_SIZE: int = Field(
        default=500,
        ge=50,
        le=4000,
        description="Chunk size for document text splitting",
    )
    RAG_CHUNK_OVERLAP: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Chunk overlap for context continuity",
    )
    # Hybrid Retrieval & Scoring Settings
    VECTOR_TOP_K: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Candidate count for vector retrieval",
    )
    KEYWORD_TOP_K: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Candidate count for PostgreSQL keyword retrieval",
    )
    RAG_TOP_K: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Top-k chunks to retrieve per RAG query",
    )
    VECTOR_RETRIEVAL_WEIGHT: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Weight given to normalized vector similarity score",
    )
    KEYWORD_RETRIEVAL_WEIGHT: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Weight given to normalized keyword search score",
    )

    # Conversation Memory Settings
    MAX_CONVERSATION_MESSAGES: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum recent conversation messages to include in agent context",
    )
    MAX_CONTEXT_TOKENS: int = Field(
        default=4000,
        ge=500,
        le=32000,
        description="Maximum character/token budget for conversation history",
    )
    EMBEDDING_PROVIDER: str = Field(
        default="gemini",
        description="Embedding provider: 'gemini' or 'openai'",
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-004",
        description="Model name for generating vector embeddings",
    )

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        valid_providers = {"openai", "gemini"}
        normalized = v.strip().lower()
        if normalized not in valid_providers:
            raise ValueError(
                f"Unsupported LLM_PROVIDER '{v}'. "
                f"Supported providers: {', '.join(sorted(valid_providers))}"
            )
        return normalized

    @model_validator(mode="after")
    def validate_retrieval_weights(self) -> "Settings":
        total_weight = self.VECTOR_RETRIEVAL_WEIGHT + self.KEYWORD_RETRIEVAL_WEIGHT
        if total_weight <= 0.0:
            raise ValueError(
                "Combined VECTOR_RETRIEVAL_WEIGHT and KEYWORD_RETRIEVAL_WEIGHT must be > 0.0"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance.

    Avoids re-reading environment variables and .env file on every request.
    """
    return Settings()
