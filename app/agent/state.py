"""Typed state definition for the LangGraph agent execution."""

from typing import Any, TypedDict


class AgentState(TypedDict):
    """Execution state schema passed across nodes in the agent graph.

    STRICT PRIVACY GUARANTEE:
    - Never store API keys, bearer tokens, or user passwords in this state.
    - Only tracks operational parameters, message context, and runtime diagnostics.
    """

    messages: list[dict[str, str]]
    user_id: str
    conversation_id: str
    intent: str
    selected_provider: str
    selected_model: str
    tool_name: str | None
    tool_operation: str | None
    tool_result: dict[str, Any] | None
    error: str | None
    retry_count: int
    final_response: str | None
    citations: list[dict[str, Any]] | None
