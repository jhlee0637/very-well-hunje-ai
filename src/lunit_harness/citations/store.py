"""Request-scoped evidence storage and MCP result extraction."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from typing import Any

from lunit_harness.citations.models import Evidence


CONTENT_KEYS = (
    "content",
    "text",
    "page_content",
    "page_text",
    "abstract",
    "answer",
    "passage",
    "description",
)
TITLE_KEYS = ("title", "document_title", "source_title", "name")
URL_KEYS = ("url", "source_url", "link")
SOURCE_TYPE_KEYS = ("source_type", "corpus_tag", "data_source", "dataset")
TERM_PATTERN = re.compile(r"[^\W_]{2,}", re.UNICODE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+")


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def __len__(self) -> int:
        return len(self._items)

    def get(self, cite_uid: str) -> Evidence | None:
        return self._items.get(cite_uid)

    def values(self) -> tuple[Evidence, ...]:
        return tuple(self._items.values())

    def selector_candidates(
        self,
        query: str,
        *,
        limit: int,
        total_content_chars: int,
    ) -> tuple[dict[str, Any], ...]:
        """Build a compact, deterministic and diversity-aware selector catalog.

        This changes only which already-collected evidence the terminal selector can
        inspect. It does not mutate the store or trigger any additional MCP/model call.
        """

        if limit <= 0 or total_content_chars <= 0 or not self._items:
            return ()

        query_terms = self._terms(query)
        records: list[dict[str, Any]] = []
        for index, evidence in enumerate(self.values()):
            content_terms = self._terms(evidence.content)
            searchable_terms = content_terms | self._terms(
                f"{evidence.title} {evidence.source_type}"
            )
            overlap = (
                len(query_terms & searchable_terms) / len(query_terms)
                if query_terms
                else 0.0
            )
            upstream_relevance = self._bounded_relevance(evidence.relevance_score)
            record = {
                "evidence": evidence,
                "index": index,
                "content_terms": content_terms,
                "document_key": self._document_key(evidence),
                "base_score": 0.72 * overlap + 0.28 * upstream_relevance,
                "upstream_relevance": upstream_relevance,
            }

            duplicate_index = self._near_duplicate_index(records, record)
            if duplicate_index is None:
                records.append(record)
                continue
            existing = records[duplicate_index]
            if self._record_order(record) > self._record_order(existing):
                records[duplicate_index] = record

        chosen: list[dict[str, Any]] = []
        remaining = list(records)
        while remaining and len(chosen) < limit:
            used_families = {
                str(item["evidence"].source_type).casefold() for item in chosen
            }
            used_documents = {str(item["document_key"]) for item in chosen}

            def diversified_score(
                record: dict[str, Any],
            ) -> tuple[float, float, float, int]:
                evidence: Evidence = record["evidence"]
                if chosen:
                    novelty = min(
                        1.0
                        - self._jaccard(
                            record["content_terms"], selected["content_terms"]
                        )
                        for selected in chosen
                    )
                else:
                    novelty = 1.0
                family_bonus = (
                    1.0
                    if evidence.source_type.casefold() not in used_families
                    else 0.0
                )
                document_bonus = (
                    1.0 if record["document_key"] not in used_documents else 0.0
                )
                score = (
                    0.72 * record["base_score"]
                    + 0.16 * novelty
                    + 0.08 * family_bonus
                    + 0.04 * document_bonus
                )
                return (
                    score,
                    record["base_score"],
                    record["upstream_relevance"],
                    -record["index"],
                )

            selected = max(remaining, key=diversified_score)
            remaining.remove(selected)
            chosen.append(selected)

        excerpt_limit = max(1, total_content_chars // max(1, len(chosen)))
        catalog: list[dict[str, Any]] = []
        for record in chosen:
            evidence: Evidence = record["evidence"]
            catalog.append(
                {
                    "cite_uid": evidence.cite_uid,
                    "source_type": evidence.source_type,
                    "title": evidence.title,
                    "retrieval_score": evidence.relevance_score,
                    "content": self._best_passage(
                        evidence.content, query_terms, excerpt_limit
                    ),
                }
            )
        return tuple(catalog)

    def add(self, evidence: Evidence) -> bool:
        if evidence.cite_uid in self._items:
            return False
        self._items[evidence.cite_uid] = evidence
        return True

    def add_mcp_result(
        self,
        result: dict[str, Any],
        *,
        tool_name: str,
        arguments_fingerprint: str,
    ) -> int:
        roots: list[Any] = []
        structured = result.get("structuredContent")
        if structured is not None:
            roots.append(structured)
        for block in result.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text = block["text"]
                try:
                    roots.append(json.loads(text))
                except json.JSONDecodeError:
                    pass

        added = 0
        for candidate in self._candidate_objects(roots):
            cite_uid = candidate.get("cite_uid")
            if not isinstance(cite_uid, str) or not cite_uid.strip():
                continue
            content = self._first_text(candidate, CONTENT_KEYS)
            if not content:
                content = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
            evidence = Evidence(
                cite_uid=cite_uid.strip(),
                source_type=self._first_text(candidate, SOURCE_TYPE_KEYS) or tool_name,
                title=self._first_text(candidate, TITLE_KEYS) or "Untitled source",
                url=self._first_text(candidate, URL_KEYS),
                content=content,
                tool_name=tool_name,
                arguments_fingerprint=arguments_fingerprint,
                relevance_score=self._score(candidate),
            )
            if self.add(evidence):
                added += 1
        return added

    @classmethod
    def _candidate_objects(cls, roots: Iterable[Any]) -> Iterable[dict[str, Any]]:
        stack = list(roots)
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if "cite_uid" in value:
                    yield value
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))

    @staticmethod
    def _score(candidate: dict[str, Any]) -> float | None:
        raw = candidate.get("relevance_score", candidate.get("score"))
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        value = float(raw)
        return value if math.isfinite(value) else None

    @staticmethod
    def _bounded_relevance(value: float | None) -> float:
        if value is None or not math.isfinite(value):
            return 0.0
        return min(1.0, max(0.0, value))

    @staticmethod
    def _terms(value: str) -> frozenset[str]:
        return frozenset(
            match.group(0).casefold() for match in TERM_PATTERN.finditer(value)
        )

    @staticmethod
    def _document_key(evidence: Evidence) -> str:
        if evidence.url.strip():
            return "url:" + " ".join(evidence.url.casefold().split())
        return "title:" + " ".join(evidence.title.casefold().split())

    @staticmethod
    def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
        if not left and not right:
            return 1.0
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    @classmethod
    def _near_duplicate_index(
        cls, records: list[dict[str, Any]], candidate: dict[str, Any]
    ) -> int | None:
        for index, existing in enumerate(records):
            if existing["document_key"] != candidate["document_key"]:
                continue
            similarity = cls._jaccard(
                existing["content_terms"], candidate["content_terms"]
            )
            if similarity >= 0.88:
                return index
        return None

    @staticmethod
    def _record_order(record: dict[str, Any]) -> tuple[float, float, int]:
        return (
            record["base_score"],
            record["upstream_relevance"],
            -record["index"],
        )

    @classmethod
    def _best_passage(
        cls, content: str, query_terms: frozenset[str], char_limit: int
    ) -> str:
        text = content.strip()
        if len(text) <= char_limit:
            return text
        sentences = [
            part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()
        ]
        if not sentences:
            sentences = [text]
        windows = [
            " ".join(sentences[index : index + 2])
            for index in range(len(sentences))
        ]

        def passage_score(item: tuple[int, str]) -> tuple[int, float, int]:
            index, passage = item
            terms = cls._terms(passage)
            overlap = len(query_terms & terms)
            density = overlap / max(1, len(terms))
            return overlap, density, -index

        _, passage = max(enumerate(windows), key=passage_score)
        if len(passage) <= char_limit:
            return passage
        folded = passage.casefold()
        positions = [
            position
            for term in query_terms
            if (position := folded.find(term)) >= 0
        ]
        start = max(0, min(positions) - char_limit // 3) if positions else 0
        return passage[start : start + char_limit].strip()

    @staticmethod
    def _first_text(candidate: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
