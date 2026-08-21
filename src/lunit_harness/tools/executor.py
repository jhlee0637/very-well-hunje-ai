"""Validated and repetition-safe MCP tool execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from lunit_harness.citations.store import EvidenceStore
from lunit_harness.clients.mcp_client import MCPClient, MCPTool
from lunit_harness.config import Settings
from lunit_harness.errors import MCPError
from lunit_harness.tools.registry import ToolRegistry


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    content: str
    evidence_added: int
    fingerprint: str
    is_error: bool = False


class ToolExecutor:
    def __init__(
        self, client: MCPClient, registry: ToolRegistry, settings: Settings
    ) -> None:
        self.client = client
        self.registry = registry
        self.settings = settings

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        fingerprints: dict[str, int],
        store: EvidenceStore,
    ) -> ToolExecutionResult:
        tool = self.registry.mcp_tool(name)
        if tool is None:
            raise ToolValidationError("unknown or non-MCP tool")
        self._validate(arguments, tool.input_schema, path="arguments")
        canonical = json.dumps(
            arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        fingerprint = hashlib.sha256(f"{name}:{canonical}".encode()).hexdigest()
        count = fingerprints.get(fingerprint, 0) + 1
        fingerprints[fingerprint] = count
        if count > self.settings.duplicate_tool_call_limit:
            raise ToolValidationError("duplicate tool call blocked")

        try:
            result = await self.client.call_tool(name, arguments)
        except MCPError as exc:
            return ToolExecutionResult(
                content=json.dumps(
                    {"error": {"code": exc.code, "message": exc.message}},
                    ensure_ascii=False,
                ),
                evidence_added=0,
                fingerprint=fingerprint,
                is_error=True,
            )

        evidence_added = store.add_mcp_result(
            result,
            tool_name=name,
            arguments_fingerprint=f"sha256:{fingerprint}",
        )
        content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(content) > self.settings.mcp_result_char_limit:
            content = content[: self.settings.mcp_result_char_limit].rstrip() + (
                "\n[tool result truncated by harness]"
            )
        return ToolExecutionResult(
            content=content,
            evidence_added=evidence_added,
            fingerprint=fingerprint,
            is_error=bool(result.get("isError")),
        )

    @classmethod
    def _validate(cls, value: Any, schema: dict[str, Any], *, path: str) -> None:
        expected = schema.get("type")
        if expected == "object":
            if not isinstance(value, dict):
                raise ToolValidationError(f"{path} must be an object")
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    raise ToolValidationError(f"{path}.{key} is required")
            if schema.get("additionalProperties") is False:
                unknown = set(value) - set(properties)
                if unknown:
                    raise ToolValidationError(f"{path} has unsupported properties")
            for key, item in value.items():
                child = properties.get(key)
                if isinstance(child, dict):
                    cls._validate(item, child, path=f"{path}.{key}")
        elif expected == "array":
            if not isinstance(value, list):
                raise ToolValidationError(f"{path} must be an array")
            child = schema.get("items")
            if isinstance(child, dict):
                for index, item in enumerate(value):
                    cls._validate(item, child, path=f"{path}[{index}]")
        elif expected == "string" and not isinstance(value, str):
            raise ToolValidationError(f"{path} must be a string")
        elif expected == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ToolValidationError(f"{path} must be an integer")
        elif expected == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ToolValidationError(f"{path} must be a number")
        elif expected == "boolean" and not isinstance(value, bool):
            raise ToolValidationError(f"{path} must be a boolean")

        if "enum" in schema and value not in schema["enum"]:
            raise ToolValidationError(f"{path} is not an allowed value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                raise ToolValidationError(f"{path} is below minimum")
            if "maximum" in schema and value > schema["maximum"]:
                raise ToolValidationError(f"{path} is above maximum")
