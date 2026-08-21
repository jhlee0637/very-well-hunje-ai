"""Pydantic models for the public OpenAI-compatible API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: Any = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, (str, list, dict)):
            raise ValueError("message content must be a string, object, array, or null")
        return value


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = Field(default=None, gt=0)
    max_completion_tokens: int | None = Field(default=None, gt=0)
    stop: str | list[str] | None = None

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not value:
            raise ValueError("messages must contain at least one message")
        if not any(message.role == "user" for message in value):
            raise ValueError("messages must contain at least one user message")
        return value

    def as_driver_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
