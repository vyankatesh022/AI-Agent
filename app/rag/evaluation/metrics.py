"""Quantitative evaluation metrics for retrieval relevance, citations, and grounding."""

import logging
from typing import Any

from app.rag.citations import SourceReference
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalMetrics:
    """Metrics assessing candidate retrieval quality."""

    @staticmethod
    def _matches_expected(
        retrieved_filename: str,
        retrieved_page: int,
        expected_sources: list[dict[str, Any]],
    ) -> bool:
        fn_clean = retrieved_filename.strip().lower()
        for exp in expected_sources:
            exp_fn = exp.get("filename", "").strip().lower()
            exp_page = int(exp.get("page", 1))
            if fn_clean == exp_fn and (exp_page == 0 or exp_page == retrieved_page):
                return True
        return False

    @classmethod
    def recall_at_k(
        cls,
        retrieved: list[RetrievalResult],
        expected_sources: list[dict[str, Any]],
        k: int = 4,
    ) -> float:
        """Proportion of expected sources found in top-k retrieved candidates."""
        if not expected_sources:
            return 1.0 if not retrieved else 1.0

        top_k_candidates = retrieved[:k]
        hits = 0
        for exp in expected_sources:
            exp_fn = exp.get("filename", "").strip().lower()
            exp_page = int(exp.get("page", 1))
            found = any(
                r.filename.strip().lower() == exp_fn
                and (exp_page == 0 or r.page_number == exp_page)
                for r in top_k_candidates
            )
            if found:
                hits += 1

        return hits / len(expected_sources)

    @classmethod
    def precision_at_k(
        cls,
        retrieved: list[RetrievalResult],
        expected_sources: list[dict[str, Any]],
        k: int = 4,
    ) -> float:
        """Proportion of top-k candidates that correspond to expected sources."""
        top_k_candidates = retrieved[:k]
        if not top_k_candidates:
            return 1.0 if not expected_sources else 0.0

        if not expected_sources:
            return 1.0 if not top_k_candidates else 0.0

        relevant_count = sum(
            1
            for r in top_k_candidates
            if cls._matches_expected(r.filename, r.page_number, expected_sources)
        )
        return relevant_count / len(top_k_candidates)

    @classmethod
    def hit_rate_at_k(
        cls,
        retrieved: list[RetrievalResult],
        expected_sources: list[dict[str, Any]],
        k: int = 4,
    ) -> float:
        """1.0 if at least one expected source is retrieved (or both empty), else 0.0."""
        if not expected_sources:
            return 1.0 if not retrieved else 1.0

        top_k_candidates = retrieved[:k]
        has_hit = any(
            cls._matches_expected(r.filename, r.page_number, expected_sources)
            for r in top_k_candidates
        )
        return 1.0 if has_hit else 0.0


class CitationMetrics:
    """Metrics evaluating citation correctness and adherence."""

    @staticmethod
    def citation_validity(
        valid_citations_count: int,
        invalid_citations_count: int,
    ) -> float:
        """Ratio of verified citations to total citations produced."""
        total = valid_citations_count + invalid_citations_count
        if total == 0:
            return 1.0
        return valid_citations_count / total

    @staticmethod
    def citation_relevance(
        cited_sources: list[SourceReference],
        expected_sources: list[dict[str, Any]],
    ) -> float:
        """Ratio of cited sources that match expected benchmark sources."""
        if not expected_sources:
            return 1.0 if not cited_sources else 0.0

        if not cited_sources:
            return 0.0

        hits = 0
        for cs in cited_sources:
            fn = cs.filename.strip().lower()
            if any(
                exp.get("filename", "").strip().lower() == fn
                and (exp.get("page", 0) == 0 or exp.get("page", 0) == cs.page_number)
                for exp in expected_sources
            ):
                hits += 1

        return hits / len(cited_sources)


class GroundingMetrics:
    """Deterministic factual coverage evaluator."""

    @staticmethod
    def fact_coverage(
        answer_text: str,
        expected_facts: list[str],
    ) -> float:
        """Measure what percentage of benchmark facts appear in the generated response."""
        if not expected_facts:
            return 1.0

        if not answer_text or not answer_text.strip():
            return 0.0

        ans_lower = answer_text.lower()
        matched_facts = sum(1 for fact in expected_facts if fact.lower() in ans_lower)
        return matched_facts / len(expected_facts)
