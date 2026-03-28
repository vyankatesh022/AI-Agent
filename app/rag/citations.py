"""Provenance citation dataclasses and formatters for RAG responses."""

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Verifiable reference to a specific source document page and chunk."""

    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CitationBuilder:
    """Constructs structured citations from retrieved chunks."""

    @staticmethod
    def build_citations(
        chunks_with_scores: list[tuple[dict[str, Any], float]],
    ) -> list[Citation]:
        """Transform search results into structured citations.

        Args:
            chunks_with_scores: List of (chunk_dict, score) tuples.

        Returns:
            List of unique Citation objects.
        """
        citations: list[Citation] = []
        seen = set()

        for chunk_meta, _ in chunks_with_scores:
            doc_id = str(chunk_meta.get("document_id", ""))
            filename = chunk_meta.get("filename", "unknown.pdf")
            page_num = int(chunk_meta.get("page_number", 1))
            chunk_idx = int(chunk_meta.get("chunk_index", 0))
            text = chunk_meta.get("text", "")

            # Truncate snippet to 150 chars for preview
            snippet = text[:150] + "..." if len(text) > 150 else text

            key = (doc_id, page_num, chunk_idx)
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        document_id=doc_id,
                        filename=filename,
                        page_number=page_num,
                        chunk_index=chunk_idx,
                        snippet=snippet,
                    )
                )

        return citations

    @staticmethod
    def format_inline_source(filename: str, page_number: int) -> str:
        """Standard citation string format for LLM prompt instruction."""
        return f"[Source: {filename}, Page {page_number}]"
