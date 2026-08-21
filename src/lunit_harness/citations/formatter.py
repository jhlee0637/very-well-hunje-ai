"""Deterministic context shaping for the Generation tool result."""

from __future__ import annotations

import hashlib
import json
import logging
import re

from lunit_harness.citations.models import (
    AugmentedSource,
    CitationSelection,
    RetrievalResult,
)
from lunit_harness.citations.store import EvidenceStore
from lunit_harness.config import Settings


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|(?<=다\.)\s+|\n\n+")
logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-free estimate for mixed Korean and English text."""

    return max(1, (len(text) + 1) // 2)


def truncate_to_token_estimate(text: str, token_limit: int) -> str:
    if estimate_tokens(text) <= token_limit:
        return text.strip()
    char_limit = max(1, token_limit * 2)
    prefix = text[:char_limit]
    boundaries = [match.start() for match in SENTENCE_BOUNDARY.finditer(prefix)]
    if boundaries and boundaries[-1] >= char_limit // 2:
        prefix = prefix[: boundaries[-1]]
    return prefix.rstrip() + "\n[truncated]"


class CitationFormatter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def format(
        self, selection: CitationSelection, store: EvidenceStore
    ) -> RetrievalResult:
        sources: list[AugmentedSource] = []
        seen_content: set[str] = set()
        used_tokens = 0

        for item in selection.items:
            if len(sources) >= self.settings.selected_source_limit:
                break
            evidence = store.get(item.cite_uid)
            if evidence is None:
                continue
            content = truncate_to_token_estimate(
                evidence.content, self.settings.source_token_limit
            )
            digest = hashlib.sha256(
                " ".join(content.split()).encode("utf-8")
            ).hexdigest()
            if digest in seen_content:
                continue
            remaining = self.settings.augmentation_token_limit - used_tokens
            if remaining <= 0:
                break
            content = truncate_to_token_estimate(content, remaining)
            content_tokens = estimate_tokens(content)
            if content_tokens > remaining:
                break
            seen_content.add(digest)
            used_tokens += content_tokens
            sources.append(
                AugmentedSource(
                    citation_number=len(sources) + 1,
                    cite_uid=evidence.cite_uid,
                    source_type=evidence.source_type,
                    title=evidence.title,
                    url=evidence.url,
                    content=content,
                )
            )

        status = selection.status
        note = selection.note
        if not sources:
            status = "no_evidence"
            note = note or "No validated citation evidence was selected."
        elif status == "no_evidence":
            status = "partial"
        logger.info(
            "augmentation status=%s selector_items=%d selected_sources=%d "
            "content_chars=%d estimated_tokens=%d",
            status,
            len(selection.items),
            len(sources),
            sum(len(source.content) for source in sources),
            used_tokens,
        )
        return RetrievalResult(status=status, note=note, sources=tuple(sources))

    def as_tool_content(
        self, selection: CitationSelection, store: EvidenceStore
    ) -> str:
        result = self.format(selection, store)
        return json.dumps(result.as_dict(), ensure_ascii=False, separators=(",", ":"))
