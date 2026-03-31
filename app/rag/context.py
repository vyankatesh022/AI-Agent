"""Context assembly service formatting retrieved document chunks for LLM consumption."""

import logging
from typing import Any

from app.rag.citations import SourceReference
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Formats retrieved chunks into clean, structured context blocks with source IDs."""

    @classmethod
    def build_context_with_sources(
        cls,
        items: list[RetrievalResult] | list[tuple[dict[str, Any], float]],
        max_characters: int = 8000,
    ) -> tuple[str, dict[str, SourceReference]]:
        """Format retrieval candidates into delimited blocks and build authoritative source map.

        Args:
            items: List of RetrievalResult objects or legacy (chunk_meta, score) tuples.
            max_characters: Maximum characters allowed in context.

        Returns:
            Tuple of (formatted_context_string, source_map) where source_map maps
            'S1', 'S2'... to authoritative SourceReference instances.
        """
        if not items:
            return "", {}

        context_blocks: list[str] = []
        source_map: dict[str, SourceReference] = {}
        current_len = 0

        for idx, item in enumerate(items, start=1):
            source_id = f"S{idx}"

            if isinstance(item, RetrievalResult):
                doc_id = item.document_id
                filename = item.filename
                page_num = item.page_number
                chunk_id = item.chunk_id
                content = item.content.strip()
                score = item.combined_score
            else:
                chunk_meta, score = item
                doc_id = str(chunk_meta.get("document_id", ""))
                filename = chunk_meta.get("filename", "unknown.pdf")
                page_num = int(chunk_meta.get("page_number", 1))
                chunk_id = str(chunk_meta.get("chunk_id", ""))
                content = chunk_meta.get("text", "").strip()

            snippet = content[:150] + "..." if len(content) > 150 else content
            ref = SourceReference(
                source_id=source_id,
                document_id=doc_id,
                filename=filename,
                page_number=page_num,
                chunk_id=chunk_id,
                snippet=snippet,
            )

            block = (
                f"[DOCUMENT SOURCE {source_id}]\n"
                f"Document: {filename}\n"
                f"Page: {page_num}\n"
                f"Relevance: {score:.2f}\n"
                f"Content:\n{content}\n"
            )

            if current_len + len(block) > max_characters and context_blocks:
                logger.info(
                    "Context reached length budget (%d chars); stopping at %d chunks",
                    max_characters,
                    idx - 1,
                )
                break

            context_blocks.append(block)
            source_map[source_id] = ref
            current_len += len(block)

        return "\n".join(context_blocks), source_map

    @classmethod
    def build_context(
        cls,
        chunks_with_scores: list[tuple[dict[str, Any], float]] | list[RetrievalResult],
        max_characters: int = 8000,
    ) -> str:
        """Backward-compatible context string generation."""
        context_str, _ = cls.build_context_with_sources(
            items=chunks_with_scores,
            max_characters=max_characters,
        )
        return context_str
