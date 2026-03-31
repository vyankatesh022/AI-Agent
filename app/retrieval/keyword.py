"""PostgreSQL-native full-text keyword retriever with strict tenant isolation."""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)


class KeywordRetriever:
    """Retrieves document chunks using PostgreSQL full-text search (tsvector + ts_rank_cd)."""

    def __init__(self, db_session: Session | None = None) -> None:
        self.settings = get_settings()
        self._db = db_session

    def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        db: Session | None = None,
    ) -> list[RetrievalResult]:
        """Query PostgreSQL full-text search index scoped strictly to user_id.

        Args:
            user_id: Authenticated user ID (strictly isolated).
            query: Natural language query or exact keyword string.
            top_k: Maximum candidate chunks to retrieve.
            db: Optional active SQLAlchemy session.

        Returns:
            List of RetrievalResult instances with normalized keyword_score.
        """
        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        limit = top_k or self.settings.KEYWORD_TOP_K
        session = db or self._db
        if session is None:
            # Fallback to fresh session if none supplied
            session_generator = get_db()
            session = next(session_generator)

        sql = text(
            """
            SELECT
                dc.id AS chunk_id,
                dc.document_id AS document_id,
                dc.user_id AS user_id,
                dc.chunk_index AS chunk_index,
                dc.page_number AS page_number,
                dc.content AS content,
                d.original_filename AS filename,
                ts_rank_cd(dc.search_vector, plainto_tsquery('english', :query)) AS rank
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.user_id = :user_id
              AND (
                  dc.search_vector @@ plainto_tsquery('english', :query)
                  OR dc.content ILIKE :exact_like
              )
            ORDER BY rank DESC, dc.created_at DESC
            LIMIT :limit;
            """
        )

        params = {
            "query": clean_query,
            "exact_like": f"%{clean_query}%",
            "user_id": user_id,
            "limit": limit,
        }

        try:
            rows = session.execute(sql, params).mappings().all()
        except Exception as exc:
            logger.error("Keyword retrieval error in PostgreSQL: %s", exc)
            return []

        if not rows:
            return []

        # Find max rank for min-max normalization
        ranks = [float(r["rank"]) for r in rows if r["rank"] is not None]
        max_rank = max(ranks) if ranks and max(ranks) > 0 else 1.0

        results: list[RetrievalResult] = []
        for row in rows:
            raw_rank = float(row["rank"]) if row["rank"] is not None else 0.0

            # Normalize keyword score to [0.0, 1.0]
            if raw_rank > 0.0:
                norm_score = max(0.1, min(1.0, raw_rank / max_rank))
            else:
                # Matched via exact ILIKE substring
                norm_score = 0.5

            res = RetrievalResult(
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                user_id=str(user_id),
                content=row["content"],
                page_number=int(row["page_number"]),
                chunk_index=int(row["chunk_index"]),
                filename=row["filename"],
                vector_score=0.0,
                keyword_score=norm_score,
                combined_score=norm_score,
                metadata={
                    "document_id": str(row["document_id"]),
                    "page_number": int(row["page_number"]),
                    "chunk_index": int(row["chunk_index"]),
                    "filename": row["filename"],
                    "raw_keyword_rank": raw_rank,
                },
            )
            results.append(res)

        logger.debug(
            "KeywordRetriever found %d candidates for user %s with query: '%s'",
            len(results),
            user_id,
            clean_query[:50],
        )
        return results
