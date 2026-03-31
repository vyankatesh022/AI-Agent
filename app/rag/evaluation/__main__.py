"""CLI entry point for running RAG evaluation benchmark."""

import asyncio
import sys

from app.rag.evaluation.evaluator import RAGEvaluator
from app.rag.evaluation.reports import EvaluationReportFormatter


async def main() -> int:
    """Run RAG evaluation benchmarks and exit with appropriate status code."""
    evaluator = RAGEvaluator()
    report = await evaluator.evaluate()
    print(EvaluationReportFormatter.format_console(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
