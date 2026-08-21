"""Minimal Streamable HTTP MCP client for the Lunit retrieval server."""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import dataclass
from typing import Any

import httpx

from lunit_harness import __version__
from lunit_harness.clients.tls import create_tls_context
from lunit_harness.config import Settings
from lunit_harness.errors import ConfigurationError, MCPError


@dataclass(frozen=True, slots=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class MCPClient:
    protocol_version = "2025-06-18"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            verify=create_tls_context(),
            timeout=httpx.Timeout(settings.mcp_timeout_seconds)
        )
        self._request_ids = itertools.count(1)
        self._initialization_lock = asyncio.Lock()
        self._initialized = False
        self._tools: tuple[MCPTool, ...] | None = None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialization_lock:
            if self._initialized:
                return
            result = await self._rpc(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "lunit-team-a-harness",
                        "version": __version__,
                    },
                },
            )
            negotiated = result.get("protocolVersion")
            if not isinstance(negotiated, str):
                raise MCPError("mcp_protocol_error", "MCP initialize omitted protocolVersion")
            self.protocol_version = negotiated
            self._initialized = True

    async def list_tools(self) -> tuple[MCPTool, ...]:
        await self.initialize()
        if self._tools is not None:
            return self._tools
        result = await self._rpc("tools/list", {})
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise MCPError("mcp_protocol_error", "MCP tools/list omitted tools")
        tools: list[MCPTool] = []
        for raw in raw_tools:
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                continue
            schema = raw.get("inputSchema", {"type": "object", "properties": {}})
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            tools.append(
                MCPTool(
                    name=raw["name"],
                    description=str(raw.get("description", "")),
                    input_schema=schema,
                )
            )
        if not tools:
            raise MCPError("mcp_protocol_error", "MCP server returned no usable tools")
        self._tools = tuple(tools)
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.initialize()
        return await self._rpc("tools/call", {"name": name, "arguments": arguments})

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.model_api_key:
            raise ConfigurationError("Lunit MCP credential is not configured")
        request_id = next(self._request_ids)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.model_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol_version,
        }
        try:
            response = await self._client.post(
                self.settings.mcp_url, headers=headers, json=payload
            )
        except httpx.TimeoutException as exc:
            raise MCPError("mcp_timeout", "MCP request timed out") from exc
        except httpx.HTTPError as exc:
            raise MCPError("mcp_unavailable", "MCP endpoint is unavailable") from exc
        if response.status_code >= 400:
            raise MCPError(
                "mcp_http_error", f"MCP endpoint returned HTTP {response.status_code}"
            )

        envelope = self._decode_response(response)
        if envelope.get("id") != request_id:
            raise MCPError("mcp_protocol_error", "MCP response id did not match request")
        error = envelope.get("error")
        if isinstance(error, dict):
            code = error.get("code", "unknown")
            raise MCPError("mcp_rpc_error", f"MCP JSON-RPC error {code}")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise MCPError("mcp_protocol_error", "MCP response omitted result")
        return result

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        try:
            if "text/event-stream" not in content_type:
                value = response.json()
                if isinstance(value, dict):
                    return value
                raise ValueError("JSON-RPC response is not an object")

            data_events: list[str] = []
            current: list[str] = []
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    current.append(line[5:].lstrip())
                elif not line and current:
                    data_events.append("\n".join(current))
                    current = []
            if current:
                data_events.append("\n".join(current))
            for data in reversed(data_events):
                value = json.loads(data)
                if isinstance(value, dict):
                    return value
        except (ValueError, json.JSONDecodeError) as exc:
            raise MCPError("mcp_protocol_error", "MCP returned invalid JSON") from exc
        raise MCPError("mcp_protocol_error", "MCP SSE response contained no data event")
