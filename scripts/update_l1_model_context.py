#!/usr/bin/env python3
"""Refresh the agent-readable L1 model snapshot without downloading model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_ID = "learning-unit/L1-16B-A3B"
DEFAULT_REVISION = "main"
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "doc" / "models" / "L1-16B-A3B.json"
MAX_INSPECT_BYTES = 1_000_000
INSPECT_FILES = (
    "config.json",
    "generation_config.json",
    "tokenizer_config.json",
    "chat_template.jinja",
    "configuration_gravity_moe.py",
    "modeling_gravity_moe.py",
)


def fetch_bytes(url: str) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lunit-hackathon-model-context/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.read(MAX_INSPECT_BYTES + 1), headers


def fetch_json(url: str) -> Any:
    payload, _ = fetch_bytes(url)
    if len(payload) > MAX_INSPECT_BYTES:
        raise ValueError(f"JSON response exceeds {MAX_INSPECT_BYTES} bytes: {url}")
    return json.loads(payload.decode("utf-8"))


def safe_file_summary(revision: str, path: str) -> dict[str, Any]:
    url = f"https://huggingface.co/{MODEL_ID}/resolve/{revision}/{path}"
    payload, headers = fetch_bytes(url)
    if len(payload) > MAX_INSPECT_BYTES:
        raise ValueError(f"Refusing to inspect large file: {path}")

    summary: dict[str, Any] = {
        "path": path,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "etag": headers.get("etag"),
    }
    if path.endswith(".json"):
        summary["content"] = json.loads(payload.decode("utf-8"))
    return summary


def refresh(revision: str) -> dict[str, Any]:
    model_api = fetch_json(f"https://huggingface.co/api/models/{MODEL_ID}")
    resolved_revision = model_api.get("sha") or revision
    siblings = model_api.get("siblings") or []
    files = [
        {
            "path": item.get("rfilename"),
            "size_bytes": item.get("size"),
            "blob_id": item.get("blobId"),
            "lfs": item.get("lfs"),
            "mirrored": False,
        }
        for item in siblings
        if item.get("rfilename")
    ]

    inspected: dict[str, Any] = {}
    available = {item["path"] for item in files}
    for path in INSPECT_FILES:
        if path in available:
            inspected[path] = safe_file_summary(resolved_revision, path)

    config = inspected.get("config.json", {}).get("content", {})
    previous = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    previous["source"].update(
        {
            "revision": resolved_revision,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "license": model_api.get("cardData", {}).get("license"),
        }
    )
    previous["config"] = config
    previous["upstream_files"] = files
    previous["inspected_files"] = inspected
    return previous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fetch and validate without writing the snapshot.",
    )
    args = parser.parse_args()

    try:
        snapshot = refresh(args.revision)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        print(
            f"validated {MODEL_ID}@{snapshot['source']['revision']} "
            f"({len(snapshot['upstream_files'])} files)"
        )
        return 0

    SNAPSHOT_PATH.write_text(encoded, encoding="utf-8")
    print(f"updated {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

