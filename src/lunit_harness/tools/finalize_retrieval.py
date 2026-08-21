"""Validation for the local Retrieval termination tool."""

from __future__ import annotations

import math
from typing import Any

from lunit_harness.citations.models import CitationItem, CitationSelection
from lunit_harness.citations.store import EvidenceStore


class FinalizeValidationError(ValueError):
    pass


def finalize_retrieval(
    arguments: dict[str, Any], store: EvidenceStore
) -> CitationSelection:
    status = arguments.get("status")
    if status not in {"sufficient", "partial", "no_evidence"}:
        raise FinalizeValidationError("invalid retrieval status")
    note = arguments.get("note", "")
    if not isinstance(note, str):
        raise FinalizeValidationError("note must be a string")
    raw_items = arguments.get("items")
    if not isinstance(raw_items, list):
        raise FinalizeValidationError("items must be an array")

    items: list[CitationItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise FinalizeValidationError("each item must be an object")
        cite_uid = raw.get("cite_uid")
        score = raw.get("relevance_score")
        if not isinstance(cite_uid, str) or not cite_uid:
            raise FinalizeValidationError("cite_uid must be a non-empty string")
        if cite_uid in seen:
            raise FinalizeValidationError("duplicate cite_uid")
        if store.get(cite_uid) is None:
            raise FinalizeValidationError("cite_uid was not returned by an MCP tool")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise FinalizeValidationError("relevance_score must be a number")
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise FinalizeValidationError("relevance_score must be between 0 and 1")
        seen.add(cite_uid)
        items.append(CitationItem(cite_uid=cite_uid, relevance_score=score))

    if status == "sufficient" and not items:
        raise FinalizeValidationError("sufficient requires at least one item")
    if status == "no_evidence" and items:
        raise FinalizeValidationError("no_evidence requires empty items")
    if status == "partial" and not items:
        status = "no_evidence"
    return CitationSelection(status=status, items=tuple(items), note=note.strip())
