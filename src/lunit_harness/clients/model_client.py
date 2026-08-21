"""Async OpenAI-compatible client for Lunit L2."""

from __future__ import annotations

from typing import Any

import httpx

from lunit_harness.clients.tls import create_tls_context
from lunit_harness.config import Settings
from lunit_harness.errors import (
    ConfigurationError,
    ModelProtocolError,
    ModelTimeoutError,
    ModelUpstreamError,
)


class ModelClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            verify=create_tls_context(),
            timeout=httpx.Timeout(settings.model_timeout_seconds)
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.model_api_key:
            raise ConfigurationError("Lunit model API credential is not configured")

        payload: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": self.settings.model_max_tokens,
        }
        if options:
            for key in (
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "stop",
            ):
                if key in options and options[key] is not None:
                    payload[key] = options[key]
        if "max_completion_tokens" in payload:
            payload.pop("max_tokens", None)
        if tools:
            payload["tools"] = tools
            payload["parallel_tool_calls"] = False

        try:
            response = await self._client.post(
                f"{self.settings.model_api_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.model_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Lunit model request timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelUpstreamError("Lunit model endpoint is unavailable") from exc

        if response.status_code >= 400:
            raise ModelUpstreamError(
                f"Lunit model endpoint returned HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelProtocolError("Lunit model returned invalid JSON") from exc

        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ModelProtocolError("Lunit model response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ModelProtocolError("Lunit model response has no assistant message")
        return body
