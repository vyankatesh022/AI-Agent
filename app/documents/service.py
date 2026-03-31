"""Document management service orchestrating ingestion, indexing, and lifecycle."""

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.documents.chunker import DocumentChunker
from app.documents.embeddings import BaseEmbeddingProvider, EmbeddingFactory
from app.documents.extractor import DocumentExtractor
from app.documents.index import UserFAISSIndex
from app.documents.storage import DocumentStorage
from app.documents.validator import DocumentValidator
from app.models import Document, DocumentChunkModel

logger = logging.getLogger(__name__)


class DocumentService:
    """Service orchestrating document validation, storage, extraction, chunking, and FAISS indexing."""

    def __init__(
        self,
        storage: DocumentStorage | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.settings = get_settings()
        self.storage = storage or DocumentStorage(self.settings.DOCUMENT_STORAGE_PATH)
        self.embedding_provider = embedding_provider

    def _get_embedding_provider(self) -> BaseEmbeddingProvider:
        if self.embedding_provider is not None:
            return self.embedding_provider
        return EmbeddingFactory.create_embedding_provider()

    def process_and_store_document(
        self,
        db: Session,
        user_id: uuid.UUID,
        file_bytes: bytes,
        original_filename: str,
        content_type: str | None = None,
    ) -> Document:
        """Validate, store, extract, chunk, embed, and index an uploaded document.

        Args:
            db: Database session.
            user_id: ID of the authenticated user.
            file_bytes: Raw binary content of the PDF.
            original_filename: Client-provided filename.
            content_type: Client-provided MIME type.

        Returns:
            Created and processed Document database entity.

        Raises:
            ValueError: If validation, extraction, or processing fails.
        """
        # Step 1: Strict validation
        page_count = DocumentValidator.validate_pdf(
            content=file_bytes,
            original_filename=original_filename,
            content_type=content_type or "application/pdf",
            max_size_mb=self.settings.MAX_DOCUMENT_SIZE_MB,
        )

        # Step 2: Create DB record in 'pending' state
        doc_id = uuid.uuid4()
        document = Document(
            id=doc_id,
            user_id=user_id,
            filename=f"{doc_id}.pdf",
            original_filename=original_filename,
            content_type=content_type or "application/pdf",
            file_size=len(file_bytes),
            storage_path="",
            status="pending",
            page_count=page_count,
            chunk_count=0,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        try:
            # Step 3: Secure filesystem storage
            storage_path = self.storage.save_file(file_bytes, doc_id)
            document.storage_path = storage_path
            document.status = "processing"
            db.commit()

            # Step 4: Text extraction with page preservation
            pages = DocumentExtractor.extract_pages(file_bytes)

            # Step 5: Chunking with provenance metadata
            chunker = DocumentChunker(
                chunk_size=self.settings.RAG_CHUNK_SIZE,
                chunk_overlap=self.settings.RAG_CHUNK_OVERLAP,
            )
            chunks = chunker.chunk_document(
                document_id=doc_id,
                user_id=user_id,
                filename=original_filename,
                pages=pages,
            )

            # Step 6: Compute vector embeddings
            embedder = self._get_embedding_provider()
            chunk_texts = [c.text for c in chunks]
            embeddings = embedder.embed_texts(chunk_texts)

            # Step 7a: Persist chunks into PostgreSQL for authoritative storage and full-text keyword search
            chunk_models = []
            for c in chunks:
                chunk_uuid = (
                    uuid.UUID(c.chunk_id)
                    if isinstance(c.chunk_id, str) and len(c.chunk_id) == 36
                    else uuid.uuid4()
                )
                c.chunk_id = str(chunk_uuid)
                chunk_model = DocumentChunkModel(
                    id=chunk_uuid,
                    document_id=doc_id,
                    user_id=user_id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    content=c.text,
                    search_vector=func.to_tsvector("english", c.text),
                )
                chunk_models.append(chunk_model)
            db.add_all(chunk_models)
            db.commit()

            # Step 7b: Index chunks into user's isolated FAISS index
            user_index = UserFAISSIndex(
                user_id=user_id,
                base_dir=self.settings.FAISS_INDEX_PATH,
                dimension=embedder.dimension,
            )
            user_index.add_chunks(chunks, embeddings)

            # Step 8: Update document to 'ready'
            document.status = "ready"
            document.chunk_count = len(chunks)
            db.commit()
            db.refresh(document)
            logger.info(
                "Successfully processed document %s (%d chunks, %d pages)",
                doc_id,
                len(chunks),
                page_count,
            )
            return document

        except Exception as exc:
            logger.exception("Failed processing document %s: %s", doc_id, exc)
            document.status = "failed"
            document.processing_error = str(exc)
            db.commit()
            db.refresh(document)
            # Re-raise so the endpoint or caller can report appropriate HTTP status
            raise ValueError(f"Document processing failed: {exc}") from exc

    def list_user_documents(
        self,
        db: Session,
        user_id: uuid.UUID,
    ) -> Sequence[Document]:
        """List all documents owned by the specified user."""
        return (
            db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def get_user_document(
        self,
        db: Session,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> Document | None:
        """Fetch a specific document owned by the user."""
        return (
            db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user_id)
            .first()
        )

    def delete_user_document(
        self,
        db: Session,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> bool:
        """Purge document from database, disk storage, and FAISS index.

        Args:
            db: Database session.
            user_id: User requesting deletion.
            document_id: UUID of document to delete.

        Returns:
            True if deleted, False if document was not found or unowned.
        """
        doc = self.get_user_document(db, user_id, document_id)
        if not doc:
            return False

        # 1. Purge from user FAISS index
        try:
            embedder = self._get_embedding_provider()
            user_index = UserFAISSIndex(
                user_id=user_id,
                base_dir=self.settings.FAISS_INDEX_PATH,
                dimension=embedder.dimension,
            )
            user_index.delete_document(document_id)
        except Exception as exc:
            logger.warning(
                "Error pruning FAISS index for document %s: %s", document_id, exc
            )

        # 2. Delete file from storage
        if doc.storage_path:
            self.storage.delete_file(doc.storage_path)

        # 3. Delete from DB
        db.delete(doc)
        db.commit()
        logger.info(
            "Successfully deleted document %s for user %s", document_id, user_id
        )
        return True
