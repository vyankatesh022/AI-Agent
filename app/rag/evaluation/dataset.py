"""Evaluation dataset definitions, test cases, and synthetic document fixtures."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class EvaluationCase:
    """Individual RAG benchmark test case."""

    case_id: str
    question: str
    expected_sources: list[dict[str, Any]]
    expected_facts: list[str]
    retrieval_type: str  # 'semantic', 'keyword', 'hybrid', 'no_match'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Synthetic evaluation documents content for deterministic evaluation
EVALUATION_DOCUMENTS: list[dict[str, Any]] = [
    {
        "filename": "handbook.pdf",
        "text": (
            "Antigravity System Architecture Handbook. "
            "The primary architectural goal of Antigravity is high scalability, "
            "zero container overhead, and strict tenant isolation. "
            "Engineering teams must deploy services using native Python and Uvicorn. "
            "All background jobs are managed via persistent scheduled timers."
        ),
    },
    {
        "filename": "policy.pdf",
        "text": (
            "Corporate Data Retention and Refund Policy. "
            "Customers are entitled to a full refund within 30 days of initial purchase. "
            "The retention period for inactive user accounts is exactly 90 days. "
            "After 90 days of inactivity, all user-owned records and vector indexes "
            "are purged irrevocably from the primary cluster."
        ),
    },
]

# Benchmark evaluation cases
DEFAULT_EVALUATION_CASES: list[EvaluationCase] = [
    EvaluationCase(
        case_id="case_semantic_01",
        question="What is the main design objective of the Antigravity backend?",
        expected_sources=[{"filename": "handbook.pdf", "page": 1}],
        expected_facts=["scalability", "tenant isolation"],
        retrieval_type="semantic",
    ),
    EvaluationCase(
        case_id="case_keyword_02",
        question="What is the retention period for inactive accounts?",
        expected_sources=[{"filename": "policy.pdf", "page": 1}],
        expected_facts=["90 days", "retention period"],
        retrieval_type="keyword",
    ),
    EvaluationCase(
        case_id="case_hybrid_03",
        question="What is the policy regarding refund requests and deadlines?",
        expected_sources=[{"filename": "policy.pdf", "page": 1}],
        expected_facts=["refund", "30 days"],
        retrieval_type="hybrid",
    ),
    EvaluationCase(
        case_id="case_negative_04",
        question="What is the internal recipe for quantum interstellar propulsion?",
        expected_sources=[],
        expected_facts=["could not find"],
        retrieval_type="no_match",
    ),
]
