"""Document ingestion, validation, processing, and vector indexing package."""

from app.documents.chunker import DocumentChunk, DocumentChunker
from app.documents.embeddings import (
    BaseEmbeddingProvider,
    EmbeddingFactory,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.documents.extractor import DocumentExtractor
from app.documents.index import UserFAISSIndex
from app.documents.service import DocumentService
from app.documents.storage import DocumentStorage
from app.documents.validator import DocumentValidator

__all__ = [
    "BaseEmbeddingProvider",
    "DocumentChunk",
    "DocumentChunker",
    "DocumentExtractor",
    "DocumentService",
    "DocumentStorage",
    "DocumentValidator",
    "EmbeddingFactory",
    "GeminiEmbeddingProvider",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "UserFAISSIndex",
]
