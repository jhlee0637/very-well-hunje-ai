"""Top-level bounded Generation → Retrieval → Generation driver."""

from __future__ import annotations

import json
import logging
from typing import Any

from lunit_harness.citations.formatter import CitationFormatter
from lunit_harness.clients.mcp_client import MCPClient
from lunit_harness.clients.model_client import ModelClient
from lunit_harness.config import Settings
from lunit_harness.errors import InvalidRequestError, ModelProtocolError
from lunit_harness.orchestration.budgets import BudgetExceededError, RequestBudget
from lunit_harness.orchestration.conversation import assistant_message
from lunit_harness.orchestration.generation_phase import (
    RETRIEVE_TOOL,
    RETRIEVE_TOOL_NAME,
    GenerationPhase,
)
from lunit_harness.orchestration.retrieval_phase import RetrievalPhase
from lunit_harness.orchestration.routing import should_offer_retrieval
from lunit_harness.tools.retrieve_relevant_content import RetrieveRelevantContent
from lunit_harness.validation.citations import (
    citations_complete,
    retain_validly_cited_segments,
)


NO_EVIDENCE_RESPONSE = "제공된 문서에서 확인할 수 없음"
logger = logging.getLogger(__name__)

NO_EVIDENCE_FOLLOWUP = """
The evidence search completed normally but returned no usable sources.
Do not invent an exact current guideline, dose, threshold, contraindication, legal rule,
coverage criterion, or citation. State which requested evidence could not be verified.
Then give only safe high-level guidance that does not depend on the missing source, the
single highest-value clarification or verification step, and urgent safety action when
the conversation makes it relevant. Do not answer with only a fixed no-evidence phrase.
Do not add numeric citations because no source was selected.
""".strip()

CITATION_REPAIR_PROMPT = """
You repair one evidence-grounded Korean clinical answer.
Use only the supplied evidence. Keep only claims directly supported by it.
End every medical sentence or bullet with an allowed numeric citation.
Do not call tools, invent facts or citations, add a source list, or discuss the repair.
""".strip()

DIRECT_RESPONSE_INSTRUCTION = (
    "Answer the preceding user question directly now in the same language as the "
    "user. Retrieval is intentionally unavailable for this request. Do not output "
    "a tool name, pseudo-tool markup, XML, or function-call syntax. Follow the "
    "direct-answer rules in the system prompt and return only the final answer."
)

RETRIEVAL_QUERY_INSTRUCTION = (
    "When using retrieve_relevant_content, preserve every requested facet and patient "
    "detail from the preceding user message in one standalone query, including each "
    "requested decision, medication, dose or threshold, time frame, and source "
    "requirement. Do not omit one requested part to search only another. Use the "
    "native function call; do not answer from memory when evidence is explicitly "
    "requested."
)


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
        retrieval_query = ""
        retrieval_tool_content = ""
        retrieval_allowed_by_query = should_offer_retrieval(input_messages)

        while True:
            try:
                budget.add_generation_call()
            except BudgetExceededError as exc:
                raise ModelProtocolError(
                    "Generation did not produce a final answer within its call limit"
                ) from exc
            allow_retrieval = (
                retrieval_allowed_by_query
                and budget.retrieval_invocations
                < self.settings.retrieval_invocation_limit
            )
            generation_limit = (
                self.settings.repair_model_max_tokens
                if citation_repair_attempted
                else self.settings.model_max_tokens
            )
            call_options = self._bounded_options(options, generation_limit)
            call_messages = messages
            if (
                budget.generation_calls == 1
                and not retrieval_allowed_by_query
                and budget.retrieval_invocations == 0
            ):
                call_messages = [
                    *messages,
                    {"role": "user", "content": DIRECT_RESPONSE_INSTRUCTION},
                ]
            elif (
                budget.generation_calls == 1
                and retrieval_allowed_by_query
                and budget.retrieval_invocations == 0
            ):
                call_messages = [
                    *messages,
                    {"role": "user", "content": RETRIEVAL_QUERY_INSTRUCTION},
                ]
            input_chars = self._payload_chars(
                call_messages, [RETRIEVE_TOOL] if allow_retrieval else []
            )
            response = await self.generation.call(
                call_messages,
                call_options,
                allow_retrieval=allow_retrieval,
            )
            self._add_usage(aggregate_usage, response.get("usage"))
            response_usage = response.get("usage") or {}
            logger.info(
                "model_phase=%s call=%d allow_retrieval=%s input_chars=%d "
                "prompt_tokens=%s completion_tokens=%s",
                "repair" if citation_repair_attempted else "generation",
                budget.generation_calls,
                allow_retrieval,
                input_chars,
                response_usage.get("prompt_tokens", "unknown"),
                response_usage.get("completion_tokens", "unknown"),
            )
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
                        raise ModelProtocolError(
                            "Citation repair did not preserve any grounded claim"
                        )
                    citation_repair_fallback = retain_validly_cited_segments(
                        content, available_citations
                    )
                    citation_repair_attempted = True
                    labels = " ".join(
                        f"[{number}]" for number in sorted(available_citations)
                    )
                    messages = self._citation_repair_messages(
                        query=retrieval_query,
                        evidence=retrieval_tool_content,
                        draft=content,
                        labels=labels,
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

            tool_call = tool_calls[0]
            call_id = str(tool_call.get("id", "missing-tool-call-id"))
            function = tool_call.get("function")
            if not isinstance(function, dict) or function.get("name") != RETRIEVE_TOOL_NAME:
                raise ModelProtocolError("Generation emitted an unsupported tool call")
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise ModelProtocolError(
                    "Generation emitted invalid retrieval arguments"
                ) from exc
            query = arguments.get("query") if isinstance(arguments, dict) else None
            if not isinstance(query, str) or not query.strip():
                raise ModelProtocolError("Generation emitted an empty retrieval query")
            try:
                budget.add_retrieval_invocation()
                output = await self.retrieve(query.strip(), budget)
            except BudgetExceededError as exc:
                raise ModelProtocolError(
                    "Generation exceeded the retrieval invocation budget"
                ) from exc

            retrieval_query = query.strip()
            retrieval_tool_content = output.content
            self._add_usage(aggregate_usage, output.usage)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": output.content,
                }
            )
            for index, extra_tool_call in enumerate(tool_calls[1:], start=2):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(
                            extra_tool_call.get("id") or f"ignored-retrieval-{index}"
                        ),
                        "content": self._ignored_retrieval_tool_content(),
                    }
                )

            if self._is_no_evidence_tool_content(output.content):
                messages.append({"role": "user", "content": NO_EVIDENCE_FOLLOWUP})
                continue

            retrieval_was_partial = retrieval_was_partial or (
                self._retrieval_status(output.content) == "partial"
            )
            available_citations.update(self._citation_numbers(output.content))
            labels = " ".join(
                f"[{number}]" for number in sorted(available_citations)
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Answer the clinical question now using only the successful first "
                        "tool result. End every medical sentence and every bullet with a "
                        "directly supporting available numeric citation, repeating the "
                        "same citation on each supported bullet when needed. Do not add a "
                        "separate source list or a single citation for a whole list. "
                        "Available citations: "
                        + labels
                    ),
                }
            )

    @staticmethod
    def _bounded_options(options: dict[str, Any], token_limit: int) -> dict[str, Any]:
        bounded = dict(options)
        if "max_completion_tokens" in bounded:
            bounded["max_completion_tokens"] = min(
                int(bounded["max_completion_tokens"]), token_limit
            )
            bounded.pop("max_tokens", None)
        else:
            requested = bounded.get("max_tokens", token_limit)
            bounded["max_tokens"] = min(int(requested), token_limit)
        return bounded

    @staticmethod
    def _payload_chars(
        messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> int:
        return len(
            json.dumps(
                {"messages": messages, "tools": tools},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    @staticmethod
    def _citation_repair_messages(
        *, query: str, evidence: str, draft: str, labels: str
    ) -> list[dict[str, Any]]:
        repair_input = {
            "question": query,
            "allowed_citations": labels,
            "evidence": evidence,
            "draft": draft,
        }
        return [
            {"role": "system", "content": CITATION_REPAIR_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    repair_input, ensure_ascii=False, separators=(",", ":")
                ),
            },
        ]

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

    @staticmethod
    def _ignored_retrieval_tool_content() -> str:
        return json.dumps(
            {
                "status": "ignored",
                "reason": "Only the first retrieval call in one assistant turn is allowed.",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

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
