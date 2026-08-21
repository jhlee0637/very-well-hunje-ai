"""Numeric citation validity and sentence-level completeness checks."""

from __future__ import annotations

import re


CITATION_PATTERN = re.compile(r"\[(\d+)\]")
CITATION_AT_END_PATTERN = re.compile(
    r"(?:[.!?。！？]\s*)?(?:\[\d+\](?:\s*,\s*\[\d+\])*)"
    r"\s*[.!?。！？]?\s*\|?\s*$"
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+(?!\[\d+\])|\n+")
LIST_PREFIX_PATTERN = re.compile(r"^(?:[-*•]|\d+[.)])\s*")


def split_claim_segments(content: str) -> tuple[str, ...]:
    """Return answer segments that must end in an available citation."""

    claims: list[str] = []
    for raw in SENTENCE_SPLIT_PATTERN.split(content):
        segment = LIST_PREFIX_PATTERN.sub("", raw.strip()).strip()
        if not segment or segment.startswith("#"):
            continue
        if segment.endswith(":"):
            continue
        if segment.startswith("제공된 문서에서 확인할 수 없음"):
            continue
        if segment.startswith("근거 부족:"):
            continue
        claim_text = CITATION_PATTERN.sub("", segment)
        if not re.search(r"[A-Za-z가-힣]", claim_text):
            continue
        claims.append(segment)
    return tuple(claims)


def retain_validly_cited_segments(content: str, available: set[int]) -> str:
    """Drop uncited or unknown-citation segments without inventing attribution."""

    retained: list[str] = []
    for claim in split_claim_segments(content):
        cited = {int(value) for value in CITATION_PATTERN.findall(claim)}
        if cited and cited <= available and CITATION_AT_END_PATTERN.search(claim):
            retained.append(claim)
    return "\n".join(retained)


def citations_complete(content: str, available: set[int]) -> bool:
    """Require every answer segment to end in a valid numeric citation."""

    cited = {int(value) for value in CITATION_PATTERN.findall(content)}
    if not cited or not cited <= available:
        return False
    claims = split_claim_segments(content)
    return bool(claims) and all(
        CITATION_AT_END_PATTERN.search(claim) is not None for claim in claims
    )
