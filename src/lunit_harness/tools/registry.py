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


GUIDELINE_TOOLS = (
    "index_get_relevant_nodes",
    "index_get_page_content",
    "index_keyword_search",
    "index_list_documents",
    "index_get_document_structure",
)
DRUG_TOOLS = (
    "openapi_mfds_get_drug_indication",
    "adr_retrieve_drug_info",
    "openapi_mfds_check_drug_permission",
    "openapi_mfds_find_drugs_by_ingredient",
)
HIRA_TOOLS = (
    "hira_updates_search",
    "openapi_hira_get_drug_price",
    *GUIDELINE_TOOLS,
)
LAW_TOOLS = (
    "openapi_law_search",
    "openapi_law_list_articles",
    "openapi_law_get_article",
)
CODE_TOOLS = (
    "kcd_search_codes",
    "kcd_get_name",
    "openapi_hira_disease_check_code",
)
RESEARCH_TOOLS = (
    "rag_vector_query",
    "rag_sql_query",
    "rag_get_data_source_detail",
    "rag_get_all_data_sources",
    "adr_retrieve_drug_info",
)
DEFAULT_TOOLS = ("rag_vector_query", *GUIDELINE_TOOLS, *DRUG_TOOLS)

QUERY_TOOL_GROUPS = (
    (
        ("급여", "보험", "심평원", "hira", "약가", "수가", "고시", "비급여"),
        HIRA_TOOLS,
    ),
    (("법률", "법령", "조문", "법적", "law", "시행령", "시행규칙"), LAW_TOOLS),
    (
        ("kcd", "상병코드", "질병코드", "진단코드", "청구코드"),
        CODE_TOOLS,
    ),
    (
        (
            "허가",
            "식약처",
            "mfds",
            "의약품",
            "약물",
            "약의",
            "용량",
            "투여",
            "복용",
            "금기",
            "적응증",
            "성분",
            "제품",
            "drug",
            "dose",
            "dosage",
            "contraindication",
            "label",
            "dailymed",
        ),
        DRUG_TOOLS,
    ),
    (
        (
            "논문",
            "문헌",
            "연구",
            "pubmed",
            "faers",
            "부작용 신호",
            "이상사례",
            "근거 수준",
        ),
        RESEARCH_TOOLS,
    ),
    (
        (
            "가이드라인",
            "진료지침",
            "지침",
            "권고",
            "목표치",
            "임계값",
            "단계",
            "1차 치료",
            "first-line",
            "guideline",
        ),
        GUIDELINE_TOOLS,
    ),
)


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

    def openai_tools(
        self, query: str | None = None, *, mcp_tool_limit: int | None = None
    ) -> list[dict]:
        selected = self._select_mcp_tools(query)
        if mcp_tool_limit is not None:
            selected = selected[:mcp_tool_limit]
        return [
            *(tool.as_openai_tool() for tool in selected),
            FINALIZE_RETRIEVAL_TOOL,
        ]

    def _select_mcp_tools(self, query: str | None) -> tuple[MCPTool, ...]:
        if query is None:
            return self.mcp_tools

        normalized = " ".join(query.casefold().split())
        preferred_names: list[str] = []
        for signals, names in QUERY_TOOL_GROUPS:
            if any(signal in normalized for signal in signals):
                preferred_names.extend(names)
        if not preferred_names:
            preferred_names.extend(DEFAULT_TOOLS)

        by_name = {tool.name: tool for tool in self.mcp_tools}
        selected: list[MCPTool] = []
        seen: set[str] = set()
        for name in preferred_names:
            tool = by_name.get(name)
            if tool is not None and name not in seen:
                selected.append(tool)
                seen.add(name)

        # Test doubles and newly introduced MCP deployments may not use a known name.
        # Falling back only when no routed tool exists avoids silently disabling retrieval.
        return tuple(selected) if selected else self.mcp_tools
