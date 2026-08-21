from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lunit_harness.clients.mcp_client import MCPClient
from lunit_harness.config import Settings
from lunit_harness.errors import HarnessError, MCPError


async def run(call_data_sources: bool) -> int:
    settings = Settings.from_env()
    client = MCPClient(settings)
    try:
        tools = await client.list_tools()
        print(f"PASS: protocol={client.protocol_version}")
        print(f"tool_count={len(tools)}")
        print("tool_names=" + ",".join(tool.name for tool in tools))
        if call_data_sources:
            names = {tool.name for tool in tools}
            if "rag_get_all_data_sources" not in names:
                print("FAIL: rag_get_all_data_sources is unavailable")
                return 1
            result = await client.call_tool("rag_get_all_data_sources", {})
            blocks = result.get("content")
            print("PASS: rag_get_all_data_sources")
            print(f"content_block_count={len(blocks) if isinstance(blocks, list) else 0}")
            print(f"has_structured_content={isinstance(result.get('structuredContent'), dict)}")
    except (HarnessError, MCPError) as exc:
        code = getattr(exc, "code", "smoke_error")
        message = getattr(exc, "message", str(exc))
        print(f"FAIL: {code}: {message}")
        return 1
    finally:
        await client.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Lunit MCP contract smoke test")
    parser.add_argument(
        "--call-data-sources",
        action="store_true",
        help="also invoke the non-query data-source catalog tool",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.call_data_sources))


if __name__ == "__main__":
    raise SystemExit(main())
