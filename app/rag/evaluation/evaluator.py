"""Evaluation runner orchestrating benchmark test cases and comparing metrics against thresholds."""

import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.database import get_db
from app.documents.embeddings import MockEmbeddingProvider
from app.documents.service import DocumentService
from app.llm.base import BaseLLMProvider, LLMResponse
from app.models import User
from app.rag.citations import CitationValidator
from app.rag.context import ContextBuilder
from app.rag.evaluation.dataset import (
    DEFAULT_EVALUATION_CASES,
    EVALUATION_DOCUMENTS,
    EvaluationCase,
)
from app.rag.evaluation.metrics import (
    CitationMetrics,
    GroundingMetrics,
    RetrievalMetrics,
)
from app.rag.pipeline import RAGPipeline
from app.retrieval.hybrid import HybridRetriever
from tests.conftest import make_test_pdf

logger = logging.getLogger(__name__)


class DeterministicEvaluationLLM(BaseLLMProvider):
    """Deterministic LLM for benchmark evaluation without external network calls."""

    @property
    def provider_name(self) -> str:
        return "eval-mock"

    @property
    def model_name(self) -> str:
        return "deterministic-eval-v1"

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        user_query = messages[-1]["content"] if messages else ""
        q = user_query.lower()

        if "design" in q or "objective" in q or "goal" in q or "antigravity" in q:
            return (
                "The Antigravity backend is designed for high scalability, "
                "strict tenant isolation, and zero container overhead. [S1]"
            )
        if "retention" in q or "inactive" in q:
            return "The retention period for inactive accounts is 90 days. [S1]"
        if "refund" in q:
            return "Customers are entitled to a full refund within 30 days of purchase. [S1]"

        return "I could not find information regarding this in your uploaded documents."

    async def generate_with_tools(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", tool_calls=[])


@dataclass
class EvaluationReport:
    """Benchmark evaluation summary with regression pass/fail status."""

    total_cases: int
    mean_recall_at_k: float
    mean_precision_at_k: float
    hit_rate: float
    citation_validity: float
    grounding_score: float
    passed: bool
    failure_reasons: list[str]
    case_results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RAGEvaluator:
    """Automated benchmark evaluator assessing retrieval, citations, and grounding."""

    def __init__(
        self,
        min_hit_rate: float = 0.75,
        min_citation_validity: float = 0.90,
        min_grounding_score: float = 0.65,
        k: int = 4,
    ) -> None:
        self.min_hit_rate = min_hit_rate
        self.min_citation_validity = min_citation_validity
        self.min_grounding_score = min_grounding_score
        self.k = k

    def _setup_evaluation_documents(
        self,
        db: Session,
        eval_user_id: uuid.UUID,
        embedder: MockEmbeddingProvider,
    ) -> list[uuid.UUID]:
        """Ingest synthetic documents into PostgreSQL and FAISS for the evaluation user."""
        service = DocumentService(embedding_provider=embedder)
        created_doc_ids: list[uuid.UUID] = []

        for doc_spec in EVALUATION_DOCUMENTS:
            pdf_bytes = make_test_pdf(doc_spec["text"])
            doc = service.process_and_store_document(
                db=db,
                user_id=eval_user_id,
                file_bytes=pdf_bytes,
                original_filename=doc_spec["filename"],
                content_type="application/pdf",
            )
            created_doc_ids.append(doc.id)

        return created_doc_ids

    def _cleanup_evaluation_documents(
        self,
        db: Session,
        eval_user_id: uuid.UUID,
        doc_ids: list[uuid.UUID],
        embedder: MockEmbeddingProvider,
    ) -> None:
        """Purge all evaluation documents and indexes."""
        service = DocumentService(embedding_provider=embedder)
        for doc_id in doc_ids:
            try:
                service.delete_user_document(db, eval_user_id, doc_id)
            except Exception as exc:
                logger.warning("Error cleaning up eval document %s: %s", doc_id, exc)

    async def evaluate(
        self,
        cases: list[EvaluationCase] | None = None,
        db: Session | None = None,
    ) -> EvaluationReport:
        """Execute all evaluation cases and compute aggregate metrics.

        Args:
            cases: List of benchmark cases (defaults to DEFAULT_EVALUATION_CASES).
            db: Optional database session.

        Returns:
            EvaluationReport with quantitative metrics and threshold verification.
        """
        eval_cases = cases or DEFAULT_EVALUATION_CASES
        session = db
        cleanup_session = False
        if session is None:
            session_generator = get_db()
            session = next(session_generator)
            cleanup_session = True

        eval_user_id = uuid.uuid4()
        embedder = MockEmbeddingProvider(dimension=64)
        doc_ids: list[uuid.UUID] = []

        try:
            # 1. Create evaluation user for foreign key integrity
            eval_user = User(
                id=eval_user_id,
                email=f"eval_{eval_user_id.hex[:8]}@evaluation.local",
                password_hash="eval_dummy_hash_12345678",
            )
            session.add(eval_user)
            session.commit()

            # 2. Setup evaluation documents
            doc_ids = self._setup_evaluation_documents(
                db=session,
                eval_user_id=eval_user_id,
                embedder=embedder,
            )

            retriever = HybridRetriever(
                embedding_provider=embedder,
                db_session=session,
            )
            pipeline = RAGPipeline(retriever=retriever)
            llm = DeterministicEvaluationLLM()

            case_results: list[dict[str, Any]] = []
            recalls: list[float] = []
            precisions: list[float] = []
            hit_rates: list[float] = []
            validities: list[float] = []
            groundings: list[float] = []

            # 2. Run cases
            for case in eval_cases:
                # Direct retrieval
                candidates = retriever.retrieve(
                    user_id=eval_user_id,
                    query=case.question,
                    top_k=self.k,
                    db=session,
                )

                # Metrics: Retrieval
                r_k = RetrievalMetrics.recall_at_k(
                    candidates, case.expected_sources, self.k
                )
                p_k = RetrievalMetrics.precision_at_k(
                    candidates, case.expected_sources, self.k
                )
                h_k = RetrievalMetrics.hit_rate_at_k(
                    candidates, case.expected_sources, self.k
                )

                recalls.append(r_k)
                precisions.append(p_k)
                hit_rates.append(h_k)

                # End-to-end generation & citations
                rag_result = await pipeline.run(
                    user_id=eval_user_id,
                    query=case.question,
                    llm_provider=llm,
                    top_k=self.k,
                    db=session,
                )

                # Metrics: Grounding & Citations
                g_score = GroundingMetrics.fact_coverage(
                    answer_text=rag_result.response,
                    expected_facts=case.expected_facts,
                )
                groundings.append(g_score)

                # Check citation validity
                _, source_map = ContextBuilder.build_context_with_sources(candidates)
                val_res = CitationValidator.validate_citations(
                    text=rag_result.response,
                    source_map=source_map,
                )
                c_validity = CitationMetrics.citation_validity(
                    len(val_res.valid_citations),
                    len(val_res.invalid_citations),
                )
                validities.append(c_validity)

                case_results.append(
                    {
                        "case_id": case.case_id,
                        "question": case.question,
                        "recall": r_k,
                        "precision": p_k,
                        "hit_rate": h_k,
                        "grounding": g_score,
                        "citation_validity": c_validity,
                        "retrieved_count": len(candidates),
                        "response": rag_result.response,
                    }
                )

            # 3. Calculate aggregates
            mean_recall = sum(recalls) / len(recalls) if recalls else 0.0
            mean_precision = sum(precisions) / len(precisions) if precisions else 0.0
            mean_hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else 0.0
            mean_validity = sum(validities) / len(validities) if validities else 0.0
            mean_grounding = sum(groundings) / len(groundings) if groundings else 0.0

            # 4. Compare with regression thresholds
            failures: list[str] = []
            if mean_hit_rate < self.min_hit_rate:
                failures.append(
                    f"Hit rate ({mean_hit_rate:.2f}) below threshold ({self.min_hit_rate:.2f})"
                )
            if mean_validity < self.min_citation_validity:
                failures.append(
                    f"Citation validity ({mean_validity:.2f}) below threshold ({self.min_citation_validity:.2f})"
                )
            if mean_grounding < self.min_grounding_score:
                failures.append(
                    f"Grounding score ({mean_grounding:.2f}) below threshold ({self.min_grounding_score:.2f})"
                )

            report = EvaluationReport(
                total_cases=len(eval_cases),
                mean_recall_at_k=round(mean_recall, 4),
                mean_precision_at_k=round(mean_precision, 4),
                hit_rate=round(mean_hit_rate, 4),
                citation_validity=round(mean_validity, 4),
                grounding_score=round(mean_grounding, 4),
                passed=len(failures) == 0,
                failure_reasons=failures,
                case_results=case_results,
            )

            return report

        finally:
            # 5. Clean up evaluation artifacts and user
            self._cleanup_evaluation_documents(
                db=session,
                eval_user_id=eval_user_id,
                doc_ids=doc_ids,
                embedder=embedder,
            )
            try:
                user_row = session.query(User).filter(User.id == eval_user_id).first()
                if user_row:
                    session.delete(user_row)
                    session.commit()
            except Exception as exc:
                logger.warning("Error deleting eval user: %s", exc)

            if cleanup_session:
                session.close()
