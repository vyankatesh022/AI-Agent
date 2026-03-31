"""RAG evaluation subsystem providing benchmark datasets, metrics, and regression runners."""

from app.rag.evaluation.dataset import DEFAULT_EVALUATION_CASES, EvaluationCase
from app.rag.evaluation.evaluator import EvaluationReport, RAGEvaluator
from app.rag.evaluation.metrics import (
    CitationMetrics,
    GroundingMetrics,
    RetrievalMetrics,
)
from app.rag.evaluation.reports import EvaluationReportFormatter

__all__ = [
    "CitationMetrics",
    "DEFAULT_EVALUATION_CASES",
    "EvaluationCase",
    "EvaluationReport",
    "EvaluationReportFormatter",
    "GroundingMetrics",
    "RAGEvaluator",
    "RetrievalMetrics",
]
