"""Dynamic MCP tool registry plus the local finalize tool."""

from __future__ import annotations

from dataclasses import dataclass

from lunit_harness.clients.mcp_client import MCPClient, MCPTool


FINALIZE_RETRIEVAL_NAME = "finalize_retrieval"
FINALIZE_RETRIEVAL_TOOL = {
    "type": "function",
    "function": {
        "name": FINALIZE_RETRIEVAL_NAME,
        "description": (
            "Submit the final citation selection and end the retrieval phase. "
            "Only select cite_uid values returned by previous tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["sufficient", "partial", "no_evidence"],
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cite_uid": {"type": "string"},
                            "relevance_score": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["cite_uid", "relevance_score"],
                        "additionalProperties": False,
                    },
                },
                "note": {"type": "string"},
            },
            "required": ["status", "items"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True, slots=True)
class ToolRegistry:
    mcp_tools: tuple[MCPTool, ...]

    @classmethod
    async def load(cls, client: MCPClient) -> "ToolRegistry":
        return cls(mcp_tools=await client.list_tools())

    def mcp_tool(self, name: str) -> MCPTool | None:
        return next((tool for tool in self.mcp_tools if tool.name == name), None)

    def finalize_only(self) -> list[dict]:
        return [FINALIZE_RETRIEVAL_TOOL]

    def openai_tools(self) -> list[dict]:
        return [
            *(tool.as_openai_tool() for tool in self.mcp_tools),
            FINALIZE_RETRIEVAL_TOOL,
        ]
