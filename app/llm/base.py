"""Abstract base class definition for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any

from app.llm.models import LLMResponse


class BaseLLMProvider(ABC):
    """Abstract interface defining the common contract for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'openai', 'gemini')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the specific model in use."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a text completion for the given conversation messages.

        Args:
            messages: List of message dictionaries containing 'role', 'content', and optional 'image'.
            system_prompt: Optional privileged system instruction.
            **kwargs: Provider-specific inference parameters.

        Returns:
            Generated response text.
        """
        pass

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response with access to registered tool specifications.

        Args:
            messages: List of message dictionaries.
            tools: List of tool definitions or schemas bound to the model.
            system_prompt: Optional privileged system instruction.
            **kwargs: Provider-specific inference parameters.

        Returns:
            LLMResponse containing text and any requested tool calls.
        """
        pass
