"""Top-level bounded Generation → Retrieval → Generation driver."""

from __future__ import annotations

import json
from typing import Any

from lunit_harness.citations.formatter import CitationFormatter
from lunit_harness.clients.mcp_client import MCPClient
from lunit_harness.clients.model_client import ModelClient
from lunit_harness.config import Settings
from lunit_harness.errors import InvalidRequestError, ModelProtocolError
from lunit_harness.orchestration.budgets import BudgetExceededError, RequestBudget
from lunit_harness.orchestration.conversation import assistant_message
from lunit_harness.orchestration.generation_phase import (
    RETRIEVE_TOOL_NAME,
    GenerationPhase,
)
from lunit_harness.orchestration.retrieval_phase import RetrievalPhase
from lunit_harness.tools.retrieve_relevant_content import RetrieveRelevantContent
from lunit_harness.validation.citations import (
    citations_complete,
    retain_validly_cited_segments,
)


NO_EVIDENCE_RESPONSE = "제공된 문서에서 확인할 수 없음"


class HarnessDriver:
    def __init__(
        self,
        settings: Settings,
        model_client: ModelClient | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        self.settings = settings
        self.model_client = model_client or ModelClient(settings)
        self.mcp_client = mcp_client or MCPClient(settings)
        self.generation = GenerationPhase(self.model_client, settings)
        retrieval = RetrievalPhase(self.model_client, self.mcp_client, settings)
        self.retrieve = RetrieveRelevantContent(
            retrieval, CitationFormatter(settings)
        )

    async def close(self) -> None:
        await self.model_client.close()
        await self.mcp_client.close()

    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_messages = payload.get("messages")
        if not isinstance(input_messages, list) or not input_messages:
            raise InvalidRequestError("messages must be a non-empty array")
        if payload.get("stream"):
            raise InvalidRequestError("streaming responses are not supported")

        options = {
            key: payload.get(key)
            for key in (
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "stop",
            )
            if payload.get(key) is not None
        }
        budget = RequestBudget(self.settings)
        messages = self.generation.initial_messages(input_messages)
        aggregate_usage: dict[str, int] = {}
        available_citations: set[int] = set()
        retrieval_was_partial = False
        empty_response_retry_attempted = False
        citation_repair_attempted = False
        citation_repair_fallback = ""

        while True:
            try:
                budget.add_generation_call()
            except BudgetExceededError as exc:
                raise ModelProtocolError(
                    "Generation did not produce a final answer within its call limit"
                ) from exc
            response = await self.generation.call(
                messages,
                options,
                allow_retrieval=(
                    budget.retrieval_invocations
                    < self.settings.retrieval_invocation_limit
                ),
            )
            self._add_usage(aggregate_usage, response.get("usage"))
            message = assistant_message(response)
            messages.append(message)
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    if empty_response_retry_attempted:
                        raise ModelProtocolError("Generation returned an empty final answer")
                    empty_response_retry_attempted = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was empty. Follow the system "
                                "instructions now: call retrieve_relevant_content when "
                                "evidence is needed, otherwise return a non-empty final "
                                "answer. Do not explain this retry."
                            ),
                        }
                    )
                    continue
                if available_citations and not citations_complete(
                    content, available_citations
                ):
                    if citation_repair_attempted:
                        retained = retain_validly_cited_segments(
                            content, available_citations
                        )
                        if not retained:
                            retained = citation_repair_fallback
                        if retained:
                            return self._text_response(
                                response,
                                self._with_partial_notice(
                                    retained, retrieval_was_partial
                                ),
                                aggregate_usage,
                            )
                        return self._no_evidence_response(response, aggregate_usage)
                    citation_repair_fallback = retain_validly_cited_segments(
                        content, available_citations
                    )
                    citation_repair_attempted = True
                    labels = " ".join(
                        f"[{number}]" for number in sorted(available_citations)
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Rewrite the previous draft as the final answer. "
                                "Split the answer so each sentence or bullet contains "
                                "one major medical claim, and end every such sentence "
                                "or bullet with a directly supporting available numeric "
                                "citation. Use only available sources, add no unsupported "
                                "claims, and do not call tools. Available citations: "
                                + labels
                            ),
                        }
                    )
                    continue
                final = dict(response)
                if retrieval_was_partial:
                    final_choices = final.get("choices")
                    if isinstance(final_choices, list) and final_choices:
                        final_choice = dict(final_choices[0])
                        final_message = dict(final_choice.get("message") or {})
                        final_message["content"] = self._with_partial_notice(
                            content, True
                        )
                        final_choice["message"] = final_message
                        final["choices"] = [final_choice]
                final["model"] = self.settings.model_name
                if aggregate_usage:
                    final["usage"] = aggregate_usage
                return final

            for tool_call in tool_calls:
                call_id = str(tool_call.get("id", "missing-tool-call-id"))
                function = tool_call.get("function")
                if not isinstance(function, dict) or function.get("name") != RETRIEVE_TOOL_NAME:
                    return self._no_evidence_response(response, aggregate_usage)
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError):
                    arguments = {}
                query = arguments.get("query") if isinstance(arguments, dict) else None
                if not isinstance(query, str) or not query.strip():
                    return self._no_evidence_response(response, aggregate_usage)
                try:
                    budget.add_retrieval_invocation()
                    output = await self.retrieve(query.strip(), budget)
                    self._add_usage(aggregate_usage, output.usage)
                    if self._is_no_evidence_tool_content(output.content):
                        return self._no_evidence_response(response, aggregate_usage)
                    retrieval_was_partial = retrieval_was_partial or (
                        self._retrieval_status(output.content) == "partial"
                    )
                    available_citations.update(
                        self._citation_numbers(output.content)
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": output.content,
                        }
                    )
                    labels = " ".join(
                        f"[{number}]" for number in sorted(available_citations)
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Answer the clinical question now using only the tool result. "
                                "End every medical sentence and every bullet with a directly "
                                "supporting available numeric citation, repeating the same "
                                "citation on each supported bullet when needed. Do not add a "
                                "separate source list or a single citation for a whole list. "
                                "Available citations: "
                                + labels
                            ),
                        }
                    )
                except BudgetExceededError:
                    return self._no_evidence_response(response, aggregate_usage)

    @staticmethod
    def _citation_numbers(tool_content: str) -> set[int]:
        try:
            payload = json.loads(tool_content)
        except (TypeError, json.JSONDecodeError):
            return set()
        sources = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(sources, list):
            return set()
        return {
            number
            for source in sources
            if isinstance(source, dict)
            and isinstance((number := source.get("citation_number")), int)
            and not isinstance(number, bool)
            and number > 0
        }

    @staticmethod
    def _is_no_evidence_tool_content(content: str) -> bool:
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        sources = payload.get("sources")
        return (
            payload.get("status") == "no_evidence"
            or not isinstance(sources, list)
            or not sources
        )

    @staticmethod
    def _retrieval_status(content: str) -> str:
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return ""
        status = payload.get("status") if isinstance(payload, dict) else None
        return status if isinstance(status, str) else ""

    @staticmethod
    def _with_partial_notice(content: str, is_partial: bool) -> str:
        notice = "근거 부족: 제공된 문서에서 확인할 수 없음"
        if not is_partial or notice in content:
            return content
        return content.rstrip() + "\n" + notice

    def _no_evidence_response(
        self, template: dict[str, Any], aggregate_usage: dict[str, int]
    ) -> dict[str, Any]:
        return self._text_response(template, NO_EVIDENCE_RESPONSE, aggregate_usage)

    def _text_response(
        self,
        template: dict[str, Any],
        content: str,
        aggregate_usage: dict[str, int],
    ) -> dict[str, Any]:
        choices = template.get("choices")
        choice = (
            dict(choices[0])
            if isinstance(choices, list) and choices
            else {"index": 0}
        )
        choice["message"] = {"role": "assistant", "content": content}
        choice["finish_reason"] = "stop"
        final = dict(template)
        final["choices"] = [choice]
        final["model"] = self.settings.model_name
        if aggregate_usage:
            final["usage"] = aggregate_usage
        return final


    @staticmethod
    def _add_usage(total: dict[str, int], usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for key, value in usage.items():
            if isinstance(value, int) and not isinstance(value, bool):
                total[key] = total.get(key, 0) + value
