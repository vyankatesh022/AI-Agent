"""Vector-based dense retriever querying user-isolated FAISS indexes."""

import logging
import uuid

from app.config import get_settings
from app.documents.embeddings import BaseEmbeddingProvider, EmbeddingFactory
from app.documents.index import UserFAISSIndex
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retrieves document chunks using semantic dense vector similarity."""

    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider | None = None,
        base_index_dir: str | None = None,
    ) -> None:
        self.settings = get_settings()
        self.embedding_provider = embedding_provider
        self.base_index_dir = base_index_dir or self.settings.FAISS_INDEX_PATH

    def _get_embedding_provider(self) -> BaseEmbeddingProvider:
        if self.embedding_provider is not None:
            return self.embedding_provider
        return EmbeddingFactory.create_embedding_provider()

    def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Query user's FAISS index and return normalized vector search results.

        Args:
            user_id: Authenticated user ID (strictly isolated).
            query: Natural language search query.
            top_k: Number of candidates to retrieve.

        Returns:
            List of RetrievalResult instances with normalized vector_score.
        """
        if not query or not query.strip():
            return []

        limit = top_k or self.settings.VECTOR_TOP_K
        embedder = self._get_embedding_provider()
        query_vector = embedder.embed_query(query.strip())

        user_index = UserFAISSIndex(
            user_id=user_id,
            base_dir=self.base_index_dir,
            dimension=embedder.dimension,
        )

        raw_results = user_index.search(query_vector=query_vector, top_k=limit)
        results: list[RetrievalResult] = []

        for chunk_meta, score in raw_results:
            # Normalize cosine similarity (clamped between 0.0 and 1.0)
            norm_score = max(0.0, min(1.0, float(score)))

            res = RetrievalResult(
                chunk_id=str(chunk_meta.get("chunk_id", "")),
                document_id=str(chunk_meta.get("document_id", "")),
                user_id=str(user_id),
                content=chunk_meta.get("text", ""),
                page_number=int(chunk_meta.get("page_number", 1)),
                chunk_index=int(chunk_meta.get("chunk_index", 0)),
                filename=chunk_meta.get("filename", "unknown.pdf"),
                vector_score=norm_score,
                keyword_score=0.0,
                combined_score=norm_score,
                metadata=chunk_meta,
            )
            results.append(res)

        logger.debug(
            "VectorRetriever found %d candidates for user %s",
            len(results),
            user_id,
        )
        return results
