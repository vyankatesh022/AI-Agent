"""Conditional edge routing logic for the LangGraph agent."""

from app.agent.state import AgentState


def route_intent(state: AgentState) -> str:
    """Determine the next graph node based on the classified intent."""
    intent = state.get("intent", "general_chat")

    if intent == "database_query":
        return "execute_tool"

    return "normal_llm"
