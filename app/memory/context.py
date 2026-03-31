"""Boundary-enforcing context formatter distinguishing privileged and untrusted prompt sections."""

import logging

from app.memory.models import ConversationContext

logger = logging.getLogger(__name__)


class ContextFormatter:
    """Formats conversation memory and RAG context with clear boundary separation."""

    @staticmethod
    def format_agent_messages(
        system_prompt: str,
        memory_context: ConversationContext,
        current_query: str,
        retrieved_context: str | None = None,
    ) -> list[dict[str, str]]:
        """Assemble complete multi-turn message payload for the LLM.

        Guarantees:
        - System prompt is privileged and positioned first.
        - Prior conversation history is injected in sequence.
        - Retrieved context is clearly delimited as untrusted external reference.
        - Current query is attached as the latest user turn.
        """
        messages: list[dict[str, str]] = []

        # 1. Privileged System Prompt (augmented with RAG sources if present)
        full_system = system_prompt
        if retrieved_context:
            full_system += (
                "\n\n--- AUTHORITATIVE RETRIEVED SOURCES ---\n"
                f"{retrieved_context}\n"
                "-----------------------------------------\n"
                "Answer using the above sources. Cite them using [S1], [S2] format."
            )

        messages.append({"role": "system", "content": full_system})

        # 2. Prior conversation turns
        for m in memory_context.messages:
            messages.append({"role": m.role, "content": m.content})

        # 3. If current query was not already the last turn in memory, append it
        if not messages or messages[-1].get("content") != current_query:
            messages.append({"role": "user", "content": current_query})

        return messages
