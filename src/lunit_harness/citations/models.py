"""Data contracts between Retrieval and Generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


RetrievalStatus = Literal["sufficient", "partial", "no_evidence"]


@dataclass(frozen=True, slots=True)
class Evidence:
    cite_uid: str
    source_type: str
    title: str
    url: str
    content: str
    tool_name: str
    arguments_fingerprint: str
    relevance_score: float | None = None


@dataclass(frozen=True, slots=True)
class CitationItem:
    cite_uid: str
    relevance_score: float


@dataclass(frozen=True, slots=True)
class CitationSelection:
    status: RetrievalStatus
    items: tuple[CitationItem, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class AugmentedSource:
    citation_number: int
    cite_uid: str
    source_type: str
    title: str
    url: str
    content: str

    def as_dict(self) -> dict:
        return {
            "citation_number": self.citation_number,
            "cite_uid": self.cite_uid,
            "source_type": self.source_type,
            "title": self.title,
            "url": self.url,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    status: RetrievalStatus
    note: str = ""
    sources: tuple[AugmentedSource, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "note": self.note,
            "sources": [source.as_dict() for source in self.sources],
        }
