"""Google Gemini LLM provider implementation."""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.llm.base import BaseLLMProvider
from app.llm.models import LLMResponse, ToolCall


class GeminiProvider(BaseLLMProvider):
    """Provider adapter for Google Gemini models."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "Google API key must be provided when using the Gemini provider."
            )

        self._model_name = model
        self._provider_name = "gemini"
        self._client = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _convert_messages(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> list[BaseMessage]:
        lc_messages: list[BaseMessage] = []
        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        return lc_messages

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        lc_messages = self._convert_messages(messages, system_prompt)
        response = await self._client.ainvoke(lc_messages, **kwargs)
        return str(response.content)

    async def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[Any],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        lc_messages = self._convert_messages(messages, system_prompt)
        model_with_tools = self._client.bind_tools(tools)
        response = await model_with_tools.ainvoke(lc_messages, **kwargs)

        tool_calls: list[ToolCall] = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(
                    ToolCall(
                        name=tc.get("name", ""),
                        args=tc.get("args", {}),
                    )
                )

        return LLMResponse(
            content=str(response.content or ""),
            tool_calls=tool_calls,
        )
