from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lunit_harness.clients.model_client import ModelClient
from lunit_harness.config import Settings
from lunit_harness.errors import HarnessError


async def run(max_tokens: int) -> int:
    settings = Settings.from_env()
    client = ModelClient(settings)
    try:
        response = await client.chat(
            messages=[
                {
                    "role": "user",
                    "content": "Connectivity check. Reply with the single word OK.",
                }
            ],
            options={"temperature": 0.0, "max_tokens": max_tokens},
        )
    except HarnessError as exc:
        print(f"FAIL: {exc.code}: {exc.message}")
        return 1
    finally:
        await client.close()

    choice = response["choices"][0]
    message = choice.get("message", {})
    print(f"PASS: model={settings.model_name}")
    print(f"finish_reason={choice.get('finish_reason')}")
    content_nonempty = bool(str(message.get("content") or "").strip())
    tool_call_count = len(message.get("tool_calls") or [])
    print(f"content_nonempty={content_nonempty}")
    print(f"tool_call_count={tool_call_count}")
    usage = response.get("usage") or {}
    print(f"total_tokens={usage.get('total_tokens', 'unknown')}")
    if not content_nonempty and tool_call_count == 0:
        print("FAIL: model returned neither content nor tool calls")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Lunit L2 connectivity smoke test")
    parser.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()
    return asyncio.run(run(args.max_tokens))


if __name__ == "__main__":
    raise SystemExit(main())
