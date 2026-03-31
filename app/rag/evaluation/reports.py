"""Formatters for RAG evaluation reports in terminal console, Markdown, and JSON formats."""

import json

from app.rag.evaluation.evaluator import EvaluationReport


class EvaluationReportFormatter:
    """Formats EvaluationReport into human-readable and machine-readable summaries."""

    @staticmethod
    def format_console(report: EvaluationReport) -> str:
        """Render clean terminal output report."""
        status_tag = "PASSED" if report.passed else "FAILED"
        lines = [
            "=" * 60,
            "              RAG EVALUATION BENCHMARK REPORT",
            "=" * 60,
            f"Total Benchmark Cases: {report.total_cases}",
            f"Mean Recall@{4}:        {report.mean_recall_at_k:.2f}",
            f"Mean Precision@{4}:     {report.mean_precision_at_k:.2f}",
            f"Hit Rate:              {report.hit_rate:.2f}  [Threshold: >= 0.75]",
            f"Citation Validity:     {report.citation_validity:.2f}  [Threshold: >= 0.90]",
            f"Grounding Score:       {report.grounding_score:.2f}  [Threshold: >= 0.65]",
            "-" * 60,
            f"OVERALL EVALUATION STATUS: {status_tag}",
        ]

        if not report.passed:
            lines.append("REGRESSION FAILURES:")
            for reason in report.failure_reasons:
                lines.append(f"  - {reason}")

        lines.append("=" * 60)
        return "\n".join(lines)

    @staticmethod
    def format_markdown(report: EvaluationReport) -> str:
        """Render GitHub Flavored Markdown report."""
        status = "**PASSED**" if report.passed else "**FAILED**"
        lines = [
            "# RAG Evaluation Benchmark Report",
            "",
            f"**Overall Status**: {status}",
            "",
            "| Metric | Score | Minimum Threshold | Status |",
            "|---|---|---|---|",
            f"| **Hit Rate@4** | `{report.hit_rate:.2f}` | `>= 0.75` | {'PASS' if report.hit_rate >= 0.75 else 'FAIL'} |",
            f"| **Citation Validity** | `{report.citation_validity:.2f}` | `>= 0.90` | {'PASS' if report.citation_validity >= 0.90 else 'FAIL'} |",
            f"| **Grounding Score** | `{report.grounding_score:.2f}` | `>= 0.65` | {'PASS' if report.grounding_score >= 0.65 else 'FAIL'} |",
            f"| **Mean Recall@4** | `{report.mean_recall_at_k:.2f}` | - | - |",
            f"| **Mean Precision@4** | `{report.mean_precision_at_k:.2f}` | - | - |",
            "",
        ]

        if report.failure_reasons:
            lines.append("### Regression Failures")
            for f in report.failure_reasons:
                lines.append(f"- {f}")
            lines.append("")

        lines.extend(
            [
                "### Detailed Case Results",
                "",
                "| Case ID | Hit Rate | Recall | Precision | Grounding | Citations |",
                "|---|---|---|---|---|---|",
            ]
        )
        for c in report.case_results:
            lines.append(
                f"| `{c['case_id']}` | `{c['hit_rate']:.2f}` | `{c['recall']:.2f}` | "
                f"`{c['precision']:.2f}` | `{c['grounding']:.2f}` | `{c['citation_validity']:.2f}` |"
            )

        return "\n".join(lines)

    @staticmethod
    def format_json(report: EvaluationReport) -> str:
        """Serialize report to JSON."""
        return json.dumps(report.to_dict(), indent=2)
