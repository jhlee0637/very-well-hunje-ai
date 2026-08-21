"""Generation-visible handler that runs the entire Retrieval subroutine."""

from __future__ import annotations

from dataclasses import dataclass

from lunit_harness.citations.formatter import CitationFormatter
from lunit_harness.orchestration.budgets import RequestBudget
from lunit_harness.orchestration.retrieval_phase import RetrievalPhase


@dataclass(frozen=True, slots=True)
class RetrievalToolOutput:
    content: str
    usage: dict[str, int]


class RetrieveRelevantContent:
    def __init__(self, phase: RetrievalPhase, formatter: CitationFormatter):
        self.phase = phase
        self.formatter = formatter

    async def __call__(
        self, query: str, budget: RequestBudget
    ) -> RetrievalToolOutput:
        outcome = await self.phase.run(query, budget)
        return RetrievalToolOutput(
            content=self.formatter.as_tool_content(outcome.selection, outcome.store),
            usage=outcome.usage,
        )
