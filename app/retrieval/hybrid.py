"""Hybrid retriever combining dense FAISS search and PostgreSQL full-text keyword search."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.documents.embeddings import BaseEmbeddingProvider
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.models import RetrievalResult
from app.retrieval.ranking import ResultRanker
from app.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Orchestrates multi-modal retrieval across vector and keyword indices."""

    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
        ranker: ResultRanker | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        db_session: Session | None = None,
    ) -> None:
        self.settings = get_settings()
        self.vector_retriever = vector_retriever or VectorRetriever(
            embedding_provider=embedding_provider,
        )
        self.keyword_retriever = keyword_retriever or KeywordRetriever(
            db_session=db_session,
        )
        self.ranker = ranker or ResultRanker(
            vector_weight=self.settings.VECTOR_RETRIEVAL_WEIGHT,
            keyword_weight=self.settings.KEYWORD_RETRIEVAL_WEIGHT,
        )

    def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        db: Session | None = None,
    ) -> list[RetrievalResult]:
        """Execute hybrid search with parallel candidate retrieval and score fusion.

        Args:
            user_id: Authenticated user identifier (strictly isolated).
            query: User's search query string.
            top_k: Final count of merged results (defaults to RAG_TOP_K).
            db: Optional active SQLAlchemy session for keyword queries.

        Returns:
            List of deduplicated, ranked RetrievalResult objects.
        """
        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        final_k = top_k or self.settings.RAG_TOP_K

        # 1. Retrieve vector candidates
        vector_candidates = self.vector_retriever.retrieve(
            user_id=user_id,
            query=clean_query,
            top_k=self.settings.VECTOR_TOP_K,
        )

        # 2. Retrieve keyword candidates from PostgreSQL
        keyword_candidates = self.keyword_retriever.retrieve(
            user_id=user_id,
            query=clean_query,
            top_k=self.settings.KEYWORD_TOP_K,
            db=db,
        )

        # 3. Fuse, deduplicate, and re-rank
        final_results = self.ranker.merge_and_rank(
            vector_results=vector_candidates,
            keyword_results=keyword_candidates,
            top_k=final_k,
        )

        logger.info(
            "Hybrid retrieval completed: user=%s query='%s' vector_candidates=%d "
            "keyword_candidates=%d final_top_k=%d",
            user_id,
            clean_query[:50],
            len(vector_candidates),
            len(keyword_candidates),
            len(final_results),
        )

        return final_results
