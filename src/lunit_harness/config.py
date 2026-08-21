"""Validated runtime configuration with a local-only secret fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _local_api_key() -> str:
    """Read a development key without logging or exposing its value."""

    path = Path(os.getenv("LUNIT_SECRETS_FILE", "secrets.json"))
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    api = payload.get("API") if isinstance(payload, dict) else None
    if not isinstance(api, dict):
        return ""
    for key_name in ("very-well-hunje-ai_API_KEY", "jehee_API_KEY"):
        value = api.get(key_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


@dataclass(frozen=True, slots=True)
class Settings:
    model_api_url: str
    model_api_key: str
    model_name: str
    mcp_url: str
    model_timeout_seconds: float
    mcp_timeout_seconds: float
    request_timeout_seconds: float
    generation_call_limit: int
    retrieval_invocation_limit: int
    retrieval_turn_limit: int
    mcp_tool_call_limit: int
    duplicate_tool_call_limit: int
    selected_source_limit: int
    source_token_limit: int
    augmentation_token_limit: int
    model_max_tokens: int
    mcp_result_char_limit: int
    generation_prompt_path: str | None
    retrieval_prompt_path: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("LUNIT_FM_API_KEY", "").strip() or _local_api_key()
        return cls(
            model_api_url=os.getenv(
                "LUNIT_FM_API_URL", "https://model.hackathon.lunit.io"
            ).rstrip("/"),
            model_api_key=api_key,
            model_name=os.getenv("LUNIT_FM_MODEL", "Lunit/L2-preview"),
            mcp_url=os.getenv(
                "LUNIT_MCP_URL", "https://mcp.hackathon.lunit.io/mcp"
            ),
            model_timeout_seconds=_positive_float(
                "LUNIT_MODEL_TIMEOUT_SECONDS", 120.0
            ),
            mcp_timeout_seconds=_positive_float("LUNIT_MCP_TIMEOUT_SECONDS", 60.0),
            request_timeout_seconds=_positive_float(
                "LUNIT_REQUEST_TIMEOUT_SECONDS", 240.0
            ),
            generation_call_limit=_positive_int("LUNIT_GENERATION_CALL_LIMIT", 3),
            retrieval_invocation_limit=_positive_int(
                "LUNIT_RETRIEVAL_INVOCATION_LIMIT", 1
            ),
            retrieval_turn_limit=_positive_int("LUNIT_RETRIEVAL_TURN_LIMIT", 8),
            mcp_tool_call_limit=_positive_int("LUNIT_MCP_TOOL_CALL_LIMIT", 8),
            duplicate_tool_call_limit=_positive_int(
                "LUNIT_DUPLICATE_TOOL_CALL_LIMIT", 1
            ),
            selected_source_limit=_positive_int("LUNIT_SELECTED_SOURCE_LIMIT", 6),
            source_token_limit=_positive_int("LUNIT_SOURCE_TOKEN_LIMIT", 1200),
            augmentation_token_limit=_positive_int(
                "LUNIT_AUGMENTATION_TOKEN_LIMIT", 6000
            ),
            model_max_tokens=_positive_int("LUNIT_MODEL_MAX_TOKENS", 2048),
            mcp_result_char_limit=_positive_int(
                "LUNIT_MCP_RESULT_CHAR_LIMIT", 12000
            ),
            generation_prompt_path=os.getenv("LUNIT_GENERATION_PROMPT_PATH") or None,
            retrieval_prompt_path=os.getenv("LUNIT_RETRIEVAL_PROMPT_PATH") or None,
        )
