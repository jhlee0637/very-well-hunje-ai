"""Top-level bounded Generation → Retrieval → Generation driver."""

from __future__ import annotations

import json
import logging
import re
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
    remove_unknown_citations,
)


NO_EVIDENCE_RESPONSE = "제공된 문서에서 확인할 수 없음"
logger = logging.getLogger(__name__)

NO_EVIDENCE_FOLLOWUP = """
The evidence search completed normally but returned no usable sources.
Do not invent an exact current guideline, dose, threshold, contraindication, legal rule,
coverage criterion, or citation. State which requested evidence could not be verified.
Do not add any number not already supplied by the user, a named unverified treatment or
study conclusion, or instructions to start or stop a medicine. Then give only safe
high-level guidance that does not depend on the missing source, the single highest-value
clarification or verification step, and urgent safety action when the conversation makes
it relevant. Use no more than six concise sentences. Do not answer with only a fixed
no-evidence phrase.
Do not add numeric citations because no source was selected.
""".strip()

NO_EVIDENCE_REPAIR_PROMPT = """
Rewrite the previous answer because it added unsupported exact or potentially unsafe
details after the evidence search returned no sources. Preserve the user's language.
Use no numeric citation, no number absent from the user's question, no named unverified
treatment or study conclusion, and no instruction to start or stop medication. In at most
six concise sentences, state the unverified scope, give one safe high-level principle, the
best verification or clarification step, and urgent action only when clearly relevant.
""".strip()

NO_EVIDENCE_SAFE_FALLBACK = (
    "검색 근거에서 요청한 정확한 정보를 확인하지 못했습니다. "
    "확인되지 않은 용량·수치·금기·허가·급여·치료 단계를 추측해서 적용하면 안 됩니다. "
    "해당 공식 문서나 처방정보를 확인하고, 환자별 결정은 필요한 임상 정보와 함께 의료진 또는 약사에게 검증하십시오. "
    "응급 증상이 있다면 근거 확인을 기다리지 말고 즉시 지역 응급의료체계에 연락하십시오."
)

NUMERIC_FACT_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
NUMERIC_CITATION_PATTERN = re.compile(r"\[\d+\]")
NO_EVIDENCE_DISCLOSURE_PATTERN = re.compile(
    r"(?:(?:근거|문서|검색|출처).*?(?:확인|검증|찾|확보).*?"
    r"(?:못|수 없|되지 않|없)|(?:확인|검증|찾|확보).*?"
    r"(?:못|수 없|되지 않|없).*?(?:근거|문서|검색|출처)|"
    r"(?:could not|unable to).*?(?:verify|find).*?(?:evidence|source)|"
    r"(?:no|insufficient|missing).*?(?:evidence|source)|"
    r"(?:evidence|source).*?(?:not found|not verified|unavailable|insufficient))",
    re.IGNORECASE | re.DOTALL,
)
UNSAFE_NO_EVIDENCE_ACTION_PATTERN = re.compile(
    r"(?:즉시|바로).*?(?:복용|투약).*?(?:중단|끊)|"
    r"(?:복용|투약).*?(?:즉시|바로).*?(?:중단|끊)|"
    r"(?:stop|discontinue).*?(?:medicine|medication|drug)",
    re.IGNORECASE | re.DOTALL,
)

CITATION_REPAIR_PROMPT = """
You repair one evidence-grounded clinical answer. Preserve the draft's language and
audience level.
Use only the supplied evidence. Keep only claims directly supported by it.
End every medical sentence or bullet with an allowed numeric citation.
Do not call tools, invent facts or citations, add a source list, or discuss the repair.
""".strip()


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
        no_evidence_repair_attempted = False
        retrieval_had_no_evidence = False
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
                if citation_repair_attempted or no_evidence_repair_attempted
                else self.settings.model_max_tokens
            )
            call_options = self._bounded_options(options, generation_limit)
            input_chars = self._payload_chars(
                messages, [RETRIEVE_TOOL] if allow_retrieval else []
            )
            response = await self.generation.call(
                messages,
                call_options,
                allow_retrieval=allow_retrieval,
            )
            self._add_usage(aggregate_usage, response.get("usage"))
            response_usage = response.get("usage") or {}
            logger.info(
                "model_phase=%s call=%d allow_retrieval=%s input_chars=%d "
                "prompt_tokens=%s completion_tokens=%s",
                "repair"
                if citation_repair_attempted or no_evidence_repair_attempted
                else "generation",
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
                    if no_evidence_repair_attempted:
                        return self._text_response(
                            response,
                            NO_EVIDENCE_SAFE_FALLBACK,
                            aggregate_usage,
                        )
                    if citation_repair_attempted and citation_repair_fallback:
                        return self._text_response(
                            response,
                            self._with_partial_notice(
                                citation_repair_fallback,
                                retrieval_was_partial,
                            ),
                            aggregate_usage,
                        )
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
                if retrieval_had_no_evidence:
                    violations = self._no_evidence_violations(
                        content,
                        input_messages=input_messages,
                        retrieval_query=retrieval_query,
                    )
                    if violations:
                        logger.info(
                            "model_phase=no_evidence_guard violations=%s",
                            ",".join(violations),
                        )
                        if no_evidence_repair_attempted:
                            return self._text_response(
                                response,
                                NO_EVIDENCE_SAFE_FALLBACK,
                                aggregate_usage,
                            )
                        no_evidence_repair_attempted = True
                        messages.append(
                            {"role": "user", "content": NO_EVIDENCE_REPAIR_PROMPT}
                        )
                        continue
                if available_citations and not citations_complete(
                    content, available_citations
                ):
                    if citation_repair_attempted:
                        repaired_without_unknown_citations = remove_unknown_citations(
                            content, available_citations
                        )
                        candidates = [
                            candidate
                            for candidate in (
                                citation_repair_fallback,
                                repaired_without_unknown_citations,
                            )
                            if candidate.strip()
                        ]
                        if candidates:
                            preserved = max(candidates, key=len)
                            return self._text_response(
                                response,
                                self._with_partial_notice(
                                    preserved, retrieval_was_partial
                                ),
                                aggregate_usage,
                            )
                        raise ModelProtocolError(
                            "Citation repair did not preserve any answer content"
                        )
                    citation_repair_fallback = remove_unknown_citations(
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
                retrieval_had_no_evidence = True
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
    def _no_evidence_violations(
        content: str,
        *,
        input_messages: list[dict[str, Any]],
        retrieval_query: str,
    ) -> list[str]:
        input_text = " ".join(
            str(message.get("content") or "")
            for message in input_messages
            if message.get("role") == "user"
        )
        allowed_numbers = set(NUMERIC_FACT_PATTERN.findall(input_text))
        allowed_numbers.update(NUMERIC_FACT_PATTERN.findall(retrieval_query))
        allowed_numbers.update({"119", "911"})
        output_numbers = set(NUMERIC_FACT_PATTERN.findall(content))
        violations: list[str] = []
        if not NO_EVIDENCE_DISCLOSURE_PATTERN.search(content):
            violations.append("missing_no_evidence_disclosure")
        if NUMERIC_CITATION_PATTERN.search(content):
            violations.append("numeric_citation")
        if output_numbers - allowed_numbers:
            violations.append("new_numeric_fact")
        if UNSAFE_NO_EVIDENCE_ACTION_PATTERN.search(content):
            violations.append("unsafe_medication_action")
        if len(content.strip()) > 1500:
            violations.append("excessive_length")
        return violations

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
