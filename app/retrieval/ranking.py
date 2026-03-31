"""Result merging, deduplication, score normalization, and re-ranking."""

import logging

from app.config import get_settings
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)


class ResultRanker:
    """Merges and ranks multi-modal retrieval candidates using weighted score fusion."""

    def __init__(
        self,
        vector_weight: float | None = None,
        keyword_weight: float | None = None,
    ) -> None:
        settings = get_settings()
        self.vector_weight = (
            vector_weight
            if vector_weight is not None
            else settings.VECTOR_RETRIEVAL_WEIGHT
        )
        self.keyword_weight = (
            keyword_weight
            if keyword_weight is not None
            else settings.KEYWORD_RETRIEVAL_WEIGHT
        )

    def merge_and_rank(
        self,
        vector_results: list[RetrievalResult],
        keyword_results: list[RetrievalResult],
        top_k: int = 4,
    ) -> list[RetrievalResult]:
        """Deduplicate by chunk_id, compute fused scores, and return top-k sorted candidates.

        Args:
            vector_results: Candidates retrieved via vector search.
            keyword_results: Candidates retrieved via PostgreSQL keyword search.
            top_k: Total candidates to retain after ranking.

        Returns:
            List of deduplicated, ranked RetrievalResult objects.
        """
        merged_map: dict[str, RetrievalResult] = {}
        total_weight = self.vector_weight + self.keyword_weight
        if total_weight <= 0:
            total_weight = 1.0

        # 1. Process vector results
        for vr in vector_results:
            key = vr.chunk_id or f"{vr.document_id}_{vr.chunk_index}"
            meta = dict(vr.metadata)
            meta["retrieval_sources"] = ["vector"]

            combined = (self.vector_weight * vr.vector_score) / total_weight

            merged_map[key] = RetrievalResult(
                chunk_id=vr.chunk_id,
                document_id=vr.document_id,
                user_id=vr.user_id,
                content=vr.content,
                page_number=vr.page_number,
                chunk_index=vr.chunk_index,
                filename=vr.filename,
                vector_score=vr.vector_score,
                keyword_score=0.0,
                combined_score=combined,
                metadata=meta,
            )

        # 2. Merge keyword results (deduplicating by chunk identifier)
        for kr in keyword_results:
            key = kr.chunk_id or f"{kr.document_id}_{kr.chunk_index}"
            if key in merged_map:
                existing = merged_map[key]
                existing.keyword_score = kr.keyword_score
                # Recompute combined score with both vector and keyword contributions
                existing.combined_score = (
                    self.vector_weight * existing.vector_score
                    + self.keyword_weight * kr.keyword_score
                ) / total_weight
                existing.metadata["retrieval_sources"] = ["vector", "keyword"]
            else:
                meta = dict(kr.metadata)
                meta["retrieval_sources"] = ["keyword"]
                combined = (self.keyword_weight * kr.keyword_score) / total_weight

                merged_map[key] = RetrievalResult(
                    chunk_id=kr.chunk_id,
                    document_id=kr.document_id,
                    user_id=kr.user_id,
                    content=kr.content,
                    page_number=kr.page_number,
                    chunk_index=kr.chunk_index,
                    filename=kr.filename,
                    vector_score=0.0,
                    keyword_score=kr.keyword_score,
                    combined_score=combined,
                    metadata=meta,
                )

        # 3. Sort by combined_score descending
        ranked = sorted(
            merged_map.values(),
            key=lambda r: r.combined_score,
            reverse=True,
        )

        logger.debug(
            "Ranked %d unique candidates (vector=%d, keyword=%d, returning top %d)",
            len(ranked),
            len(vector_results),
            len(keyword_results),
            min(top_k, len(ranked)),
        )

        return ranked[:top_k]
