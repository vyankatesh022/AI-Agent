"""Embedding provider abstractions and factory supporting OpenAI, Gemini, and Mock models."""

from abc import ABC, abstractmethod
import hashlib
import logging
import math
from typing import ClassVar

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Abstract interface for generating vector embeddings."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a batch of text chunks."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Compute an embedding for a search query string."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimensionality."""
        pass


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embeddings provider using text-embedding models."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must be provided for embeddings.")
        self.model_name = model_name
        self._client = OpenAIEmbeddings(
            openai_api_key=api_key,
            model=model_name,
        )
        self._dim = 1536 if "3-small" in model_name or "ada" in model_name else 3072

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)

    @property
    def dimension(self) -> int:
        return self._dim


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Google Gemini embeddings provider using text-embedding models."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-004",
    ) -> None:
        if not api_key:
            raise ValueError("Google API key must be provided for embeddings.")
        
        # Ensure model is formatted properly for Google GenAI
        normalized_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
        self.model_name = normalized_model
        self._client = GoogleGenerativeAIEmbeddings(
            google_api_key=api_key,
            model=self.model_name,
        )
        self._dim = 768

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)

    @property
    def dimension(self) -> int:
        return self._dim


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, lightweight embedding provider for unit and integration testing."""

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension

    def _generate_vector(self, text: str) -> list[float]:
        """Generate a deterministic normalized unit vector from input text."""
        # Hash text to seed vector values
        vector = []
        for i in range(self._dimension):
            h = hashlib.sha256(f"{text}_{i}".encode("utf-8")).hexdigest()
            # Convert first 8 hex characters to float in [-1.0, 1.0]
            val = (int(h[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0
            vector.append(val)

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)

    @property
    def dimension(self) -> int:
        return self._dimension


class EmbeddingFactory:
    """Factory resolving configured or registered embedding providers."""

    SUPPORTED_PROVIDERS: ClassVar[set[str]] = {"openai", "gemini"}
    _custom_providers: ClassVar[dict[str, BaseEmbeddingProvider]] = {}

    @classmethod
    def register_provider(cls, name: str, provider: BaseEmbeddingProvider) -> None:
        """Register a custom/mock embedding provider for testing."""
        cls._custom_providers[name.lower()] = provider

    @classmethod
    def clear_custom_providers(cls) -> None:
        """Clear custom registered test providers."""
        cls._custom_providers.clear()

    @classmethod
    def create_embedding_provider(
        cls,
        provider_name: str | None = None,
        model_name: str | None = None,
        settings: Settings | None = None,
    ) -> BaseEmbeddingProvider:
        """Create and return an embedding provider instance."""
        app_settings = settings or get_settings()
        selected = (provider_name or app_settings.EMBEDDING_PROVIDER).strip().lower()

        # Check custom/mock providers first
        if selected in cls._custom_providers:
            return cls._custom_providers[selected]

        if selected not in cls.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported EMBEDDING_PROVIDER '{selected}'. "
                f"Supported providers: {', '.join(sorted(cls.SUPPORTED_PROVIDERS))}"
            )

        if selected == "openai":
            if not app_settings.OPENAI_API_KEY:
                raise ValueError(
                    "OPENAI_API_KEY is not configured in the application environment."
                )
            model = model_name or "text-embedding-3-small"
            return OpenAIEmbeddingProvider(
                api_key=app_settings.OPENAI_API_KEY,
                model_name=model,
            )

        if selected == "gemini":
            if not app_settings.GOOGLE_API_KEY:
                raise ValueError(
                    "GOOGLE_API_KEY is not configured in the application environment."
                )
            model = model_name or app_settings.EMBEDDING_MODEL
            return GeminiEmbeddingProvider(
                api_key=app_settings.GOOGLE_API_KEY,
                model_name=model,
            )

        raise ValueError(f"Unhandled embedding provider: {selected}")
