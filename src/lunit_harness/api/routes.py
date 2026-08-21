"""FastAPI application factory and OpenAI-compatible routes."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from lunit_harness.api.schemas import ChatCompletionRequest
from lunit_harness.config import Settings
from lunit_harness.errors import HarnessError, InvalidRequestError, MCPError
from lunit_harness.orchestration.driver import NO_EVIDENCE_RESPONSE, HarnessDriver


logger = logging.getLogger(__name__)
_logged_degraded_categories: set[str] = set()


def _degraded_chat_completion(model: str, exc: BaseException) -> JSONResponse:
    """Return a valid completion when a known runtime dependency is unavailable."""

    category = type(exc).__name__
    if category not in _logged_degraded_categories:
        _logged_degraded_categories.add(category)
        logger.warning("Serving degraded chat completion: category=%s", category)
    return JSONResponse(
        status_code=200,
        headers={"X-Lunit-Degraded": "true"},
        content={
            "id": f"chatcmpl-degraded-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": NO_EVIDENCE_RESPONSE,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        },
    )


def create_app(
    *,
    driver: HarnessDriver | Any | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    provided_driver = driver

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime_driver = provided_driver or HarnessDriver(settings or Settings.from_env())
        app.state.driver = runtime_driver
        try:
            yield
        finally:
            if provided_driver is None:
                await runtime_driver.close()

    app = FastAPI(title="Lunit L2 RAG Harness", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HarnessError)
    async def handle_harness_error(
        _request: Request, exc: HarnessError
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.as_openai_error())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = InvalidRequestError("Invalid Chat Completions request")
        return JSONResponse(status_code=400, content=error.as_openai_error())

    @app.get("/v1/models")
    async def list_models(request: Request) -> dict[str, Any]:
        runtime: HarnessDriver = request.app.state.driver
        return {
            "object": "list",
            "data": [
                {
                    "id": runtime.settings.model_name,
                    "object": "model",
                    "owned_by": "lunit",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        payload: ChatCompletionRequest, request: Request
    ) -> JSONResponse:
        if payload.stream:
            raise InvalidRequestError("Streaming responses are not supported")
        runtime: HarnessDriver = request.app.state.driver
        try:
            async with asyncio.timeout(runtime.settings.request_timeout_seconds):
                response = await runtime.complete(payload.as_driver_payload())
        except InvalidRequestError:
            raise
        except (HarnessError, MCPError, TimeoutError) as exc:
            return _degraded_chat_completion(runtime.settings.model_name, exc)
        return JSONResponse(status_code=200, content=response)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
