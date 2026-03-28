"""Factory for instantiating and managing LLM providers."""

from typing import ClassVar

from app.config import Settings, get_settings
from app.llm.base import BaseLLMProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.models import LLMProviderType
from app.llm.openai_provider import OpenAIProvider


class LLMFactory:
    """Factory creating and resolving configured LLM providers."""

    # Allowlist of supported providers and models for request-level validation
    SUPPORTED_PROVIDERS: ClassVar[set[str]] = {"openai", "gemini"}
    ALLOWED_MODELS: ClassVar[dict[str, set[str]]] = {
        "openai": {"gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"},
        "gemini": {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"},
    }

    # Registry for testing/mock provider overrides
    _custom_providers: ClassVar[dict[str, BaseLLMProvider]] = {}

    @classmethod
    def register_provider(cls, name: str, provider: BaseLLMProvider) -> None:
        """Register a custom or mock provider (useful for deterministic tests)."""
        cls._custom_providers[name.lower()] = provider

    @classmethod
    def clear_custom_providers(cls) -> None:
        """Clear custom registered test providers."""
        cls._custom_providers.clear()

    @classmethod
    def create_provider(
        cls,
        provider_name: str | None = None,
        model_name: str | None = None,
        settings: Settings | None = None,
    ) -> BaseLLMProvider:
        """Instantiate an LLM provider based on configuration or explicit request.

        Args:
            provider_name: Target provider ('openai' or 'gemini').
            model_name: Optional model override.
            settings: Settings instance.

        Raises:
            ValueError: If the provider is unsupported or credentials are missing.
        """
        app_settings = settings or get_settings()
        selected_provider = (provider_name or app_settings.LLM_PROVIDER).strip().lower()

        # Check if a custom mock provider was registered for tests
        if selected_provider in cls._custom_providers:
            return cls._custom_providers[selected_provider]

        if selected_provider not in cls.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider '{selected_provider}'. "
                f"Allowed providers: {', '.join(sorted(cls.SUPPORTED_PROVIDERS))}"
            )

        if selected_provider == LLMProviderType.OPENAI:
            if not app_settings.OPENAI_API_KEY:
                raise ValueError(
                    "OPENAI_API_KEY is not configured in the application environment."
                )
            selected_model = model_name or app_settings.OPENAI_MODEL
            return OpenAIProvider(
                api_key=app_settings.OPENAI_API_KEY,
                model=selected_model,
                timeout_seconds=app_settings.LLM_TIMEOUT_SECONDS,
                max_retries=app_settings.LLM_MAX_RETRIES,
            )

        if selected_provider == LLMProviderType.GEMINI:
            if not app_settings.GOOGLE_API_KEY:
                raise ValueError(
                    "GOOGLE_API_KEY is not configured in the application environment."
                )
            selected_model = model_name or app_settings.GEMINI_MODEL
            return GeminiProvider(
                api_key=app_settings.GOOGLE_API_KEY,
                model=selected_model,
                timeout_seconds=app_settings.LLM_TIMEOUT_SECONDS,
                max_retries=app_settings.LLM_MAX_RETRIES,
            )

        raise ValueError(f"Unrecognized provider: {selected_provider}")
