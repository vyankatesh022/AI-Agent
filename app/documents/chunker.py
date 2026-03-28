"""Document text chunker attaching rich metadata for RAG attribution."""

from dataclasses import asdict, dataclass, field
import logging
from typing import Any
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents an atomic text chunk with provenance metadata."""

    chunk_id: str
    document_id: uuid.UUID
    user_id: uuid.UUID
    page_number: int
    filename: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk into a serializable dictionary."""
        d = asdict(self)
        d["document_id"] = str(self.document_id)
        d["user_id"] = str(self.user_id)
        return d


class DocumentChunker:
    """Chunks text while preserving page boundaries and injecting source metadata."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
            keep_separator=True,
        )

    def chunk_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        pages: list[tuple[int, str]],
    ) -> list[DocumentChunk]:
        """Split extracted pages into metadata-annotated DocumentChunks.

        Args:
            document_id: Unique UUID of the parent document.
            user_id: Unique UUID of the owning user.
            filename: Client-supplied document filename.
            pages: List of (page_number, text) tuples.

        Returns:
            List of DocumentChunk instances with contiguous global indices.
        """
        chunks: list[DocumentChunk] = []
        global_chunk_idx = 0

        for page_number, page_text in pages:
            if not page_text.strip():
                continue

            text_splits = self.splitter.split_text(page_text)
            for split_text in text_splits:
                split_clean = split_text.strip()
                if not split_clean:
                    continue

                chunk_id = str(uuid.uuid4())
                meta = {
                    "chunk_id": chunk_id,
                    "document_id": str(document_id),
                    "user_id": str(user_id),
                    "page_number": page_number,
                    "filename": filename,
                    "chunk_index": global_chunk_idx,
                }

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    user_id=user_id,
                    page_number=page_number,
                    filename=filename,
                    chunk_index=global_chunk_idx,
                    text=split_clean,
                    metadata=meta,
                )
                chunks.append(chunk)
                global_chunk_idx += 1

        logger.debug(
            "Document %s chunked into %d chunks across %d pages",
            document_id,
            len(chunks),
            len(pages),
        )
        return chunks
