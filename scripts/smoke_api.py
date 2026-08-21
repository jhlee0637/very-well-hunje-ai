from __future__ import annotations

import argparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible API smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument(
        "--query",
        default="타이레놀정 500mg의 식약처 허가 적응증과 주요 금기를 근거와 함께 알려주세요.",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        with httpx.Client(timeout=300.0) as client:
            health = client.get(f"{base_url}/health")
            health.raise_for_status()
            models = client.get(f"{base_url}/v1/models")
            models.raise_for_status()
            model = models.json()["data"][0]["id"]
            print(f"PASS: health={health.json().get('status')}")
            print(f"PASS: model={model}")

            if not args.skip_chat:
                response = client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": args.query}],
                        "temperature": 0.0,
                    },
                )
                response.raise_for_status()
                body = response.json()
                choice = body["choices"][0]
                content = choice.get("message", {}).get("content") or ""
                print("PASS: chat completion")
                print(f"finish_reason={choice.get('finish_reason')}")
                print(f"content_nonempty={bool(content.strip())}")
                citation_present = "[1]" in content or "[2]" in content
                print(f"numeric_citation_present={citation_present}")
                print(f"total_tokens={(body.get('usage') or {}).get('total_tokens', 'unknown')}")
                if not citation_present:
                    print("FAIL: expected at least one validated numeric citation")
                    return 1
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
