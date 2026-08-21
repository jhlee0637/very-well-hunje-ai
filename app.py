"""OpenAI-compatible submission driver for the Lunit Hackathon."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://model.hackathon.lunit.io"
DEFAULT_MODEL = "Lunit/L2-preview"


def model_name() -> str:
    return os.environ.get("LUNIT_FM_MODEL", DEFAULT_MODEL)


def forward_chat(payload: dict, timeout: float = 180.0) -> tuple[int, dict]:
    api_key = os.environ.get("LUNIT_FM_API_KEY")
    if not api_key:
        return 503, {"error": {"message": "LUNIT_FM_API_KEY is not configured", "type": "server_error"}}

    upstream = dict(payload)
    upstream["model"] = model_name()
    request = Request(
        f"{os.environ.get('LUNIT_FM_API_URL', DEFAULT_API_URL).rstrip('/')}/v1/chat/completions",
        data=json.dumps(upstream).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {"error": {"message": str(exc), "type": "upstream_error"}}
        return exc.code, body
    except (URLError, TimeoutError) as exc:
        return 502, {"error": {"message": str(exc), "type": "upstream_error"}}


class OpenAIHandler(BaseHTTPRequestHandler):
    server_version = "LunitBaselineDriver/1.0"

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path == "/v1/models":
            name = model_name()
            self.send_json(200, {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "lunit"}]})
            return
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}})
            return
        messages = payload.get("messages")
        if not isinstance(messages, list):
            self.send_json(400, {"error": {"message": "messages must be an array", "type": "invalid_request_error"}})
            return
        status, response = forward_chat(payload)
        self.send_json(status, response)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving Lunit baseline driver on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), OpenAIHandler).serve_forever()


if __name__ == "__main__":
    main()
