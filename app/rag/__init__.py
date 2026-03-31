"""Retrieval-Augmented Generation (RAG) subsystem."""

from app.rag.citations import (
    Citation,
    CitationBuilder,
    CitationValidationResult,
    CitationValidator,
    SourceReference,
)
from app.rag.context import ContextBuilder
from app.rag.pipeline import RAGPipeline, RAGResult
from app.rag.retriever import DocumentRetriever

__all__ = [
    "Citation",
    "CitationBuilder",
    "CitationValidationResult",
    "CitationValidator",
    "ContextBuilder",
    "DocumentRetriever",
    "RAGPipeline",
    "RAGResult",
    "SourceReference",
]
