"""Conservative pre-generation gate for obviously direct-answer requests."""

from __future__ import annotations

from typing import Any


DIRECT_SIGNALS = (
    "일반적인",
    "일반 원칙",
    "고수준",
    "전형적",
    "전형적인",
    "개념",
    "정의",
    "무엇인지",
    "필요 없습니다",
    "필요하지 않",
    "general overview",
    "high-level",
    "definition",
)

RETRIEVAL_SIGNALS = (
    "출처",
    "근거",
    "인용",
    "citation",
    "가이드라인",
    "진료지침",
    "guideline",
    "최신",
    "현행",
    "공식",
    "허가",
    "식약처",
    "mfds",
    "hira",
    "급여",
    "법률",
    "법령",
    "조문",
    "kcd",
    "진단코드",
    "상병코드",
    "의약품 라벨",
    "문헌",
    "논문",
    "연구",
    "정확한",
    "정밀한",
    "용량",
    "투여량",
    "복용량",
    "mg/kg",
    "임계값",
    "목표 수치",
    "금기",
    "단계",
    "1차 치료",
    "first-line",
    "희귀",
    "비전형",
    "치료 실패",
    "불응",
    "임신",
    "수유",
    "소아",
    "신부전",
    "간부전",
)


def should_offer_retrieval(messages: list[dict[str, Any]]) -> bool:
    """Block tools only for strong direct-answer wording with no evidence signal.

    Unknown and patient-specific requests keep the tool available so the L2 model can
    still make the full routing decision. This is a cost guard, not a clinical
    classifier.
    """

    latest_user = next(
        (
            message.get("content")
            for message in reversed(messages)
            if message.get("role") == "user"
            and isinstance(message.get("content"), str)
        ),
        "",
    )
    normalized = " ".join(str(latest_user).casefold().split())
    if not normalized:
        return True
    has_direct_signal = any(signal in normalized for signal in DIRECT_SIGNALS)
    has_retrieval_signal = any(
        signal in normalized for signal in RETRIEVAL_SIGNALS
    )
    return not (has_direct_signal and not has_retrieval_signal)
