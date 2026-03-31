"""Data models for retrieval candidates, scores, and hybrid search results."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievalResult:
    """Normalized retrieval candidate with provenance and multi-modal scores."""

    chunk_id: str
    document_id: str
    user_id: str
    content: str
    page_number: int
    chunk_index: int
    filename: str
    vector_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert result into a serializable dictionary."""
        return asdict(self)
