#!/usr/bin/env python3
"""Run a retrieval-free Lunit L2 baseline through Chat Completions."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prompting import GROUNDED_SYSTEM_PROMPT, MOCK_CONTEXT, build_grounded_messages  # noqa: E402


DEFAULT_INPUT = ROOT / "data" / "baseline_questions.jsonl"
DEFAULT_SYSTEM_PROMPT = GROUNDED_SYSTEM_PROMPT


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a third-party dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument(
        "--context-file",
        type=Path,
        help="UTF-8 mock evidence file (defaults to the built-in mock guideline)",
    )
    return parser.parse_args()


def require_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def load_questions(path: Path, limit: int | None) -> list[dict]:
    questions = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            if "id" not in item or "prompt" not in item:
                raise ValueError(f"{path}:{line_number} requires id and prompt")
            questions.append(item)
            if limit is not None and len(questions) >= limit:
                break
    if not questions:
        raise ValueError(f"No questions found in {path}")
    return questions


def call_model(
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    context: str = MOCK_CONTEXT,
) -> tuple[dict, float]:
    payload = {
        "model": model,
        "messages": build_grounded_messages(
            [{"role": "user", "content": prompt}],
            context=context,
            system_prompt=system_prompt,
        ),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = Request(
        f"{endpoint.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result, time.perf_counter() - started


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    endpoint = require_env("LUNIT_FM_API_URL", "https://model.hackathon.lunit.io")
    api_key = require_env("LUNIT_FM_API_KEY")
    model = require_env("LUNIT_FM_MODEL", "Lunit/L2-preview")
    questions = load_questions(args.input, args.limit)
    context = args.context_file.read_text(encoding="utf-8") if args.context_file else MOCK_CONTEXT

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output_dir / f"baseline_{stamp}.jsonl"
    latencies: list[float] = []
    prompt_tokens = 0
    completion_tokens = 0
    successes = 0

    with output_path.open("w", encoding="utf-8") as output:
        for index, item in enumerate(questions, start=1):
            record = {
                "id": item["id"],
                "prompt": item["prompt"],
                "model": model,
                "retrieval": "mock",
                "context": context,
            }
            try:
                response, latency = call_model(
                    endpoint,
                    api_key,
                    model,
                    args.system_prompt,
                    item["prompt"],
                    args.temperature,
                    args.max_tokens,
                    args.timeout,
                    context,
                )
                usage = response.get("usage") or {}
                record.update(
                    status="ok",
                    response=response["choices"][0]["message"]["content"],
                    finish_reason=response["choices"][0].get("finish_reason"),
                    latency_seconds=round(latency, 3),
                    usage=usage,
                )
                successes += 1
                latencies.append(latency)
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                print(f"[{index}/{len(questions)}] {item['id']}: ok ({latency:.2f}s)")
            except (HTTPError, URLError, TimeoutError, KeyError, ValueError) as exc:
                detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, HTTPError) else str(exc)
                record.update(status="error", error=detail)
                print(f"[{index}/{len(questions)}] {item['id']}: error: {detail}", file=sys.stderr)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()

    summary = {
        "model": model,
        "retrieval": "mock",
        "input": str(args.input),
        "output": str(output_path),
        "total": len(questions),
        "successes": successes,
        "success_rate": successes / len(questions),
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
        },
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if successes == len(questions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
