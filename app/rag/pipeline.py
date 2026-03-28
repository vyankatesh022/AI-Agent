"""End-to-end RAG pipeline coordinating retrieval and grounded generation."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.llm.base import BaseLLMProvider
from app.rag.citations import Citation, CitationBuilder
from app.rag.context import ContextBuilder
from app.rag.retriever import DocumentRetriever

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """You are a precise, grounded AI assistant answering questions \
based STRICTLY on the provided source documents.

RULES:
1. Answer the question using ONLY the information presented in the \
SOURCE DOCUMENTS below.
2. DO NOT make assumptions or hallucinate information not in the sources.
3. If the provided sources do not contain enough information to answer the question, \
clearly state: "I could not find information regarding this in your uploaded documents."
4. Whenever you cite a fact, explicitly include the citation in this exact format: \
[Source: <filename>, Page <page_number>].
5. Keep your answer clear, accurate, and concise.

SOURCE DOCUMENTS:
{context}
"""


@dataclass
class RAGResult:
    """Result of a RAG query execution."""

    response: str
    citations: list[Citation]
    retrieved_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "citations": [c.to_dict() for c in self.citations],
            "retrieved_count": self.retrieved_count,
        }


class RAGPipeline:
    """Orchestrates retrieval, context assembly, and generation."""

    def __init__(self, retriever: DocumentRetriever | None = None) -> None:
        self.retriever = retriever or DocumentRetriever()

    async def run(
        self,
        user_id: uuid.UUID,
        query: str,
        llm_provider: BaseLLMProvider,
        top_k: int | None = None,
    ) -> RAGResult:
        """Execute end-to-end RAG for an authenticated user query.

        Args:
            user_id: Authenticated user ID (strictly isolated).
            query: User's question or search query.
            llm_provider: Instantiated LLM provider to use for generation.
            top_k: Optional limit on retrieved chunks.

        Returns:
            RAGResult containing grounded response and structured citations.
        """
        # 1. Retrieve chunks
        chunks_with_scores = self.retriever.retrieve(
            user_id=user_id,
            query=query,
            top_k=top_k,
        )

        if not chunks_with_scores:
            logger.info("No relevant chunks found for user %s query", user_id)
            return RAGResult(
                response=(
                    "I could not find any relevant information in your "
                    "uploaded documents regarding your query."
                ),
                citations=[],
                retrieved_count=0,
            )

        # 2. Build structured context and citations
        context = ContextBuilder.build_context(chunks_with_scores)
        citations = CitationBuilder.build_citations(chunks_with_scores)

        # 3. Format prompt and invoke LLM
        system_content = RAG_SYSTEM_PROMPT.format(context=context)
        messages = [
            {"role": "user", "content": query},
        ]

        logger.debug(
            "Invoking LLM for RAG response (context length: %d chars, chunks: %d)",
            len(context),
            len(chunks_with_scores),
        )
        response_text = await llm_provider.generate_response(
            messages=messages,
            system_prompt=system_content,
        )

        return RAGResult(
            response=response_text,
            citations=citations,
            retrieved_count=len(chunks_with_scores),
        )
