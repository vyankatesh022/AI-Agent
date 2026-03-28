"""Permission-aware document retriever operating over user-isolated FAISS indexes."""

import logging
import uuid
from typing import Any

from app.config import get_settings
from app.documents.embeddings import BaseEmbeddingProvider, EmbeddingFactory
from app.documents.index import UserFAISSIndex

logger = logging.getLogger(__name__)


class DocumentRetriever:
    """Retrieves relevant document chunks with strict tenant isolation."""

    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider | None = None,
        base_index_dir: str | None = None,
        default_top_k: int | None = None,
    ) -> None:
        self.settings = get_settings()
        self.embedding_provider = embedding_provider
        self.base_index_dir = base_index_dir or self.settings.FAISS_INDEX_PATH
        self.default_top_k = default_top_k or self.settings.RAG_TOP_K

    def _get_embedding_provider(self) -> BaseEmbeddingProvider:
        if self.embedding_provider is not None:
            return self.embedding_provider
        return EmbeddingFactory.create_embedding_provider()

    def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Retrieve top-k chunks matching query for the authenticated user.

        Args:
            user_id: ID of user querying documents.
            query: Natural language query string.
            top_k: Number of chunks to retrieve (defaults to config setting).

        Returns:
            List of (chunk_metadata_dict, similarity_score) tuples.
        """
        if not query or not query.strip():
            return []

        k = top_k or self.default_top_k
        embedder = self._get_embedding_provider()
        query_vector = embedder.embed_query(query.strip())

        user_index = UserFAISSIndex(
            user_id=user_id,
            base_dir=self.base_index_dir,
            dimension=embedder.dimension,
        )

        results = user_index.search(query_vector=query_vector, top_k=k)
        logger.debug(
            "Retrieved %d chunks for user %s with query: '%s'",
            len(results),
            user_id,
            query[:50],
        )
        return results
