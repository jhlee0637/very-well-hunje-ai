"""Conversation copying and prompt loading helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


def copy_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy caller-owned messages so orchestration never mutates the API request."""

    return deepcopy(messages)


def load_prompt(path: str | None, fallback: str) -> str:
    if not path:
        return fallback.strip()
    prompt_path = Path(path)
    try:
        value = prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback.strip()
    return value or fallback.strip()


def assistant_message(response: dict[str, Any]) -> dict[str, Any]:
    raw = response["choices"][0]["message"]
    message: dict[str, Any] = {
        "role": "assistant",
        "content": raw.get("content"),
    }
    if raw.get("tool_calls"):
        message["tool_calls"] = raw["tool_calls"]
    return message
