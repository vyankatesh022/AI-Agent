"""Context assembly service formatting retrieved chunks for LLM consumption."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Formats retrieved chunks into clean, structured context blocks for prompting."""

    @staticmethod
    def build_context(
        chunks_with_scores: list[tuple[dict[str, Any], float]],
        max_characters: int = 8000,
    ) -> str:
        """Format retrieved chunks into an annotated context block.

        Args:
            chunks_with_scores: List of (chunk_dict, score) tuples.
            max_characters: Max characters in context to prevent prompt bloat.

        Returns:
            Formatted context string.
        """
        if not chunks_with_scores:
            return ""

        context_parts: list[str] = []
        current_len = 0

        for idx, (chunk, score) in enumerate(chunks_with_scores, start=1):
            filename = chunk.get("filename", "unknown.pdf")
            page_num = chunk.get("page_number", 1)
            text = chunk.get("text", "").strip()

            block = (
                f"--- SOURCE {idx}: {filename} (Page {page_num}) "
                f"[Relevance: {score:.2f}] ---\n{text}\n"
            )

            if current_len + len(block) > max_characters and context_parts:
                logger.info(
                    "Context reached length budget (%d chars); stopping at %d chunks",
                    max_characters,
                    idx - 1,
                )
                break

            context_parts.append(block)
            current_len += len(block)

        return "\n".join(context_parts)
