"""User-isolated FAISS vector index management for document chunks."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.documents.chunker import DocumentChunk

logger = logging.getLogger(__name__)


class UserFAISSIndex:
    """Manages an isolated FAISS vector index for a single authenticated user.

    Enforces:
    - Tenant isolation: Each user's vector index and metadata are stored in
      a dedicated directory `data/indexes/{user_id}/`.
    - Normalization: Vectors are L2-normalized to support exact Cosine Similarity
      via Inner Product (`IndexFlatIP`).
    - Synchronization: Vector embeddings and chunk metadata stay 1:1 mapped.
    - Safe Deletion: When documents are deleted, chunks and vectors are pruned
      and the index is rebuilt atomically.
    """

    def __init__(
        self,
        user_id: uuid.UUID,
        base_dir: str = "data/indexes",
        dimension: int = 768,
    ) -> None:
        self.user_id = user_id
        self.dimension = dimension
        self.base_path = Path(base_dir).resolve()
        self.user_dir = (self.base_path / str(user_id)).resolve()

        # Path traversal guard
        if not self.user_dir.is_relative_to(self.base_path):
            raise ValueError("Path traversal attempt in user index path.")

        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.user_dir / "index.faiss"
        self.meta_file = self.user_dir / "metadata.json"
        self.vectors_file = self.user_dir / "vectors.npy"

        self.index: faiss.IndexFlatIP | None = None
        self.chunks_metadata: list[dict[str, Any]] = []
        self._vectors: np.ndarray | None = None

        self.load()

    def load(self) -> None:
        """Load user index and metadata from disk if present, else create empty index."""
        if (
            self.index_file.exists()
            and self.meta_file.exists()
            and self.vectors_file.exists()
        ):
            try:
                self.index = faiss.read_index(str(self.index_file))
                with open(self.meta_file, encoding="utf-8") as f:
                    self.chunks_metadata = json.load(f)
                self._vectors = np.load(str(self.vectors_file))
                logger.debug(
                    "Loaded existing index for user %s with %d vectors",
                    self.user_id,
                    self.index.ntotal,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Failed to load existing index for user %s; initializing empty index: %s",
                    self.user_id,
                    exc,
                )

        # Initialize fresh empty index
        self.index = faiss.IndexFlatIP(self.dimension)
        self.chunks_metadata = []
        self._vectors = np.empty((0, self.dimension), dtype=np.float32)

    def save(self) -> None:
        """Persist index, vectors, and metadata files to user directory."""
        if self.index is None or self._vectors is None:
            return

        # Write FAISS index
        faiss.write_index(self.index, str(self.index_file))

        # Write metadata
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self.chunks_metadata, f, ensure_ascii=False, indent=2)

        # Write vectors
        np.save(str(self.vectors_file), self._vectors)
        logger.debug(
            "Saved index and metadata for user %s (%d vectors)",
            self.user_id,
            self.index.ntotal,
        )

    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        """Add document chunks and corresponding embeddings to the user index.

        Args:
            chunks: List of DocumentChunk objects.
            embeddings: Parallel list of float vector embeddings.
        """
        if not chunks or not embeddings:
            return

        if len(chunks) != len(embeddings):
            raise ValueError("Chunks count must match embeddings count.")

        vec_arr = np.array(embeddings, dtype=np.float32)
        if vec_arr.shape[1] != self.dimension:
            # If loaded dimension does not match incoming dimension (e.g. provider switch),
            # re-initialize index with new dimension
            if self.index is None or self.index.ntotal == 0:
                self.dimension = vec_arr.shape[1]
                self.index = faiss.IndexFlatIP(self.dimension)
                self._vectors = np.empty((0, self.dimension), dtype=np.float32)
            else:
                raise ValueError(
                    f"Vector dimension mismatch. Index dimension: {self.dimension}, "
                    f"Embedding dimension: {vec_arr.shape[1]}"
                )

        # L2 normalize for cosine similarity
        faiss.normalize_L2(vec_arr)

        # Add to FAISS index
        self.index.add(vec_arr)

        # Append to vectors matrix
        if self._vectors is None or self._vectors.shape[0] == 0:
            self._vectors = vec_arr
        else:
            self._vectors = np.vstack([self._vectors, vec_arr])

        # Append chunk metadata
        for chunk in chunks:
            chunk_dict = chunk.to_dict()
            self.chunks_metadata.append(chunk_dict)

        self.save()

    def search(
        self,
        query_vector: list[float],
        top_k: int = 4,
    ) -> list[tuple[dict[str, Any], float]]:
        """Search top-k most similar chunks for the user.

        Args:
            query_vector: Embedding vector for search query.
            top_k: Number of nearest chunks to retrieve.

        Returns:
            List of (chunk_metadata, cosine_similarity_score) tuples.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        q_arr = np.array([query_vector], dtype=np.float32)
        if q_arr.shape[1] != self.dimension:
            logger.warning(
                "Query dimension (%d) does not match index dimension (%d)",
                q_arr.shape[1],
                self.dimension,
            )
            return []

        faiss.normalize_L2(q_arr)

        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(q_arr, k)

        results: list[tuple[dict[str, Any], float]] = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx >= 0 and idx < len(self.chunks_metadata):
                results.append((self.chunks_metadata[idx], float(score)))

        return results

    def delete_document(self, document_id: uuid.UUID) -> int:
        """Remove all chunks associated with a document and rebuild the index.

        Args:
            document_id: UUID of the document to purge.

        Returns:
            Count of chunks deleted.
        """
        if not self.chunks_metadata:
            return 0

        target_doc_str = str(document_id)
        keep_indices: list[int] = []
        deleted_count = 0

        for idx, meta in enumerate(self.chunks_metadata):
            if meta.get("document_id") == target_doc_str:
                deleted_count += 1
            else:
                keep_indices.append(idx)

        if deleted_count == 0:
            return 0

        logger.info(
            "Purging %d chunks for document %s from user %s index",
            deleted_count,
            document_id,
            self.user_id,
        )

        # Update metadata
        self.chunks_metadata = [self.chunks_metadata[i] for i in keep_indices]

        # Update vectors & rebuild FAISS index
        self.index = faiss.IndexFlatIP(self.dimension)
        if keep_indices and self._vectors is not None:
            self._vectors = self._vectors[keep_indices]
            self.index.add(self._vectors)
        else:
            self._vectors = np.empty((0, self.dimension), dtype=np.float32)

        self.save()
        return deleted_count
