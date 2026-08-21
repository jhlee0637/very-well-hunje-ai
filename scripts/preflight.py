from __future__ import annotations

import ast
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lunit_harness.config import Settings


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    passes: list[str] = []

    required = [
        "Dockerfile",
        ".dockerignore",
        ".env.example",
        "requirements.txt",
        "app.py",
        "prompts/generation/production_tool_v1.md",
        "prompts/generation/production_tool_v2.md",
        "prompts/generation/production_tool_v3.md",
        "prompts/retrieval/grounded_v1.md",
        "src/lunit_harness/api/routes.py",
        "src/lunit_harness/orchestration/driver.py",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        failures.append("missing required files: " + ", ".join(missing))
    else:
        passes.append("required submission files")

    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    required_ignores = ["secrets.json", ".env", "CODEX_HISTORY*", ".venv", "tests"]
    absent_ignores = [item for item in required_ignores if item not in dockerignore]
    if absent_ignores:
        failures.append(".dockerignore missing: " + ", ".join(absent_ignores))
    else:
        passes.append("Docker secret/development exclusions")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "COPY . " in dockerfile or "COPY .\n" in dockerfile:
        failures.append("Dockerfile must not copy the entire worktree")
    else:
        passes.append("Dockerfile copies allowlisted runtime files")

    syntax_errors: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")) + [ROOT / "app.py"]:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeError) as exc:
            syntax_errors.append(f"{path.relative_to(ROOT)}: {exc}")
    if syntax_errors:
        failures.extend(syntax_errors)
    else:
        passes.append("Python source syntax")

    for package in ("fastapi", "httpx", "pydantic", "uvicorn"):
        try:
            importlib.import_module(package)
        except ImportError:
            failures.append(f"missing Python dependency: {package}")
    if not any(item.startswith("missing Python dependency") for item in failures):
        passes.append("runtime Python imports")

    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--", "secrets.json", "CODEX_HISTORY_JEHEE.log"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        tracked = None
    if tracked is None or tracked.returncode != 0:
        warnings.append("git tracking check unavailable")
    elif tracked.stdout.strip():
        failures.append("local secret/history files are tracked by Git")
    else:
        passes.append("secret/history files are untracked")

    try:
        configured = bool(Settings.from_env().model_api_key)
    except (OSError, ValueError):
        configured = False
    if configured:
        passes.append("runtime credential is available (value hidden)")
    else:
        warnings.append("LUNIT_FM_API_KEY is not configured")

    docker = shutil.which("docker")
    if docker:
        contexts = []
        configured_context = os.getenv("LUNIT_DOCKER_CONTEXT", "").strip()
        if configured_context:
            contexts.append(configured_context)
        contexts.extend(["", "desktop-linux"])
        seen: set[str] = set()
        engine_version = ""
        engine_context = ""
        for context in contexts:
            if context in seen:
                continue
            seen.add(context)
            command = [docker]
            if context:
                command.extend(["--context", context])
            command.extend(["info", "--format", "{{.ServerVersion}}"])
            try:
                checked = subprocess.run(
                    command,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if checked.returncode == 0 and checked.stdout.strip():
                engine_version = checked.stdout.strip()
                engine_context = context or "current"
                break
        if engine_version:
            passes.append(f"Docker engine {engine_version} ({engine_context} context)")
        else:
            warnings.append("Docker CLI found but engine is unavailable")
    else:
        warnings.append("Docker CLI not found; build/run validation is pending")

    for item in passes:
        print(f"PASS: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    for item in failures:
        print(f"FAIL: {item}")
    print(f"SUMMARY: {len(passes)} pass, {len(warnings)} warning, {len(failures)} fail")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
