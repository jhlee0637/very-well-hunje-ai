"""FastAPI application factory and OpenAI-compatible routes."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from lunit_harness.api.schemas import ChatCompletionRequest
from lunit_harness.config import Settings
from lunit_harness.errors import (
    HarnessError,
    InvalidRequestError,
    MCPError,
    ModelUpstreamError,
    RequestDeadlineError,
)
from lunit_harness.orchestration.driver import HarnessDriver


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
        except MCPError as exc:
            raise ModelUpstreamError("MCP retrieval failed") from exc
        except TimeoutError as exc:
            raise RequestDeadlineError("Request deadline exceeded") from exc
        return JSONResponse(status_code=200, content=response)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
