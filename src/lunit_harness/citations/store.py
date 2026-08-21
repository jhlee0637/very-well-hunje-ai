"""Request-scoped evidence storage and MCP result extraction."""

from __future__ import annotations

import json
import math
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


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def __len__(self) -> int:
        return len(self._items)

    def get(self, cite_uid: str) -> Evidence | None:
        return self._items.get(cite_uid)

    def values(self) -> tuple[Evidence, ...]:
        return tuple(self._items.values())

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
    def _first_text(candidate: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
