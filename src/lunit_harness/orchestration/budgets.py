"""Per-request counters and a monotonic deadline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from lunit_harness.config import Settings
from lunit_harness.errors import RequestDeadlineError


class BudgetExceededError(RuntimeError):
    pass


@dataclass(slots=True)
class RequestBudget:
    settings: Settings
    started_at: float = field(default_factory=time.monotonic)
    generation_calls: int = 0
    retrieval_invocations: int = 0
    retrieval_turns: int = 0
    mcp_tool_calls: int = 0
    retrieval_input_chars: int = 0

    @property
    def deadline(self) -> float:
        return self.started_at + self.settings.request_timeout_seconds

    def check_deadline(self) -> None:
        if time.monotonic() >= self.deadline:
            raise RequestDeadlineError("Request deadline exceeded")

    def add_generation_call(self) -> None:
        self.check_deadline()
        self.generation_calls += 1
        if self.generation_calls > self.settings.generation_call_limit:
            raise BudgetExceededError("generation call limit exceeded")

    def add_retrieval_invocation(self) -> None:
        self.check_deadline()
        self.retrieval_invocations += 1
        if self.retrieval_invocations > self.settings.retrieval_invocation_limit:
            raise BudgetExceededError("retrieval invocation limit exceeded")

    def add_retrieval_turn(self) -> None:
        self.check_deadline()
        self.retrieval_turns += 1
        if self.retrieval_turns > self.settings.retrieval_turn_limit:
            raise BudgetExceededError("retrieval model turn limit exceeded")

    def add_mcp_tool_call(self) -> None:
        self.check_deadline()
        self.mcp_tool_calls += 1
        if self.mcp_tool_calls > self.settings.mcp_tool_call_limit:
            raise BudgetExceededError("MCP tool call limit exceeded")

    def can_add_retrieval_input_chars(self, amount: int, *, reserve: int = 0) -> bool:
        self.check_deadline()
        if amount < 0 or reserve < 0:
            raise ValueError("retrieval input character accounting must be non-negative")
        return (
            self.retrieval_input_chars + amount + reserve
            <= self.settings.retrieval_input_char_limit
        )

    def add_retrieval_input_chars(self, amount: int) -> None:
        if not self.can_add_retrieval_input_chars(amount):
            raise BudgetExceededError("retrieval input character limit exceeded")
        self.retrieval_input_chars += amount
