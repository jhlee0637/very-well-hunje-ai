from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lunit_harness.config import Settings
from lunit_harness.errors import HarnessError
from lunit_harness.orchestration.driver import HarnessDriver, NO_EVIDENCE_RESPONSE


async def run(query: str, requested_max_tokens: int) -> int:
    settings = Settings.from_env()
    driver = HarnessDriver(settings)
    try:
        response = await driver.complete(
            {
                "model": settings.model_name,
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.0,
                "max_tokens": requested_max_tokens,
            }
        )
    except HarnessError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, ensure_ascii=False))
        return 1
    finally:
        await driver.close()

    choice = response["choices"][0]
    content = str((choice.get("message") or {}).get("content") or "")
    usage = response.get("usage") or {}
    print(
        json.dumps(
            {
                "status": "ok",
                "content_chars": len(content),
                "has_numeric_citation": any(
                    f"[{number}]" in content for number in range(1, 10)
                ),
                "is_no_evidence": content.strip() == NO_EVIDENCE_RESPONSE,
                "finish_reason": choice.get("finish_reason"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded end-to-end harness request without printing secrets."
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()
    return asyncio.run(run(args.query, args.max_tokens))


if __name__ == "__main__":
    raise SystemExit(main())
