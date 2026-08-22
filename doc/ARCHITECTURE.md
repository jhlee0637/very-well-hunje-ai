# Lunit L2 RAG Architecture

## 1. 문서 목적과 우선순위

이 문서는 Lunit Medical AI Hackathon 제출물의 Team A 실행 아키텍처를 정의한다. 구현은 이 문서의 상태 전이, 데이터 계약, 실패 처리와 소유권 경계를 따른다.

상충하는 내용이 있으면 다음 순서로 적용한다.

1. 로컬 대회 규칙 원문(비공개)
2. `doc/SUPPORT_PARAMETER.md`
3. Repository root의 `AGENTS.md`
4. 이 문서와 로컬 Team A 작업 지침 `AGENTS_A.md`

## 2. 목표와 비목표

### 목표

- Evaluator가 전달한 전체 multi-turn `messages`를 받아 다음 assistant response를 반환한다.
- Lunit L2의 Generation 단계와 Retrieval 단계를 별도 model call로 실행한다.
- Retrieval L2가 Lunit MCP tools를 사용해 evidence를 수집하고 `finalize_retrieval`로 종료하게 한다.
- 선택된 evidence만 결정적으로 포맷해 Generation의 tool result로 전달한다.
- 모든 loop, retry, timeout, context 크기에 명시적인 상한을 둔다.
- Docker container 하나로 OpenAI-compatible API를 `0.0.0.0:8000`에서 제공한다.

### 비목표

- L2 model weight 또는 tokenizer를 다운로드하거나 image에 포함하지 않는다.
- 무제한 autonomous agent loop를 만들지 않는다.
- MVP에서 MCP corpus를 복제하거나 로컬 embedding과 DuckDB VSS index를 구축하지 않는다.
- Team A 코드에서 임상 prompt 또는 evaluation case를 소유하지 않는다.
- Server-side conversation session을 유지하지 않는다.

## 3. 핵심 원칙

1. **Generation-first:** Generation L2가 retrieval 필요 여부를 판단한다.
2. **Bounded retrieval:** Python state machine이 Retrieval L2와 MCP 호출을 제한한다.
3. **Tool-result augmentation:** 검색 context는 system prompt 문자열에 합치지 않고 `retrieve_relevant_content`의 tool result로 전달한다.
4. **Validated citations:** 실제 MCP 결과에서 수집한 `cite_uid`만 Generation context에 포함한다.
5. **Request isolation:** evidence, budgets, tool history는 요청마다 새로 생성한다.
6. **Deterministic formatting:** 같은 validated selection과 evidence store는 같은 citation block을 생성한다.
7. **Graceful degradation:** MCP 일부 실패는 가능한 범위에서 `partial` 또는 `no_evidence`로 흡수하고, model 호출 자체의 치명적 실패와 구분한다.

## 4. 전체 실행 흐름

```text
Evaluator
  → POST /v1/chat/completions
  → request validation
  → request-scoped state 생성
  → Generation L2 call
      tools = [retrieve_relevant_content]
      │
      ├─ final assistant content
      │    → response validation
      │    → OpenAI-compatible response
      │
      └─ retrieve_relevant_content(query)
           → standalone query validation
           → Retrieval L2 call loop
                tools = [Lunit MCP tools, finalize_retrieval]
                → MCP results normalize
                → EvidenceStore 축적
                → finalize_retrieval
           → CitationSelection validation
           → deterministic augmentation formatting
           → Generation tool-result message
           → Generation L2 continuation
           → response validation
           → OpenAI-compatible response
```

Generation의 tool call과 tool result는 같은 model conversation에 다음 순서로 보존한다.

```text
assistant: retrieve_relevant_content tool call
tool: validated and formatted evidence
assistant: final answer
```

## 5. OpenAI-compatible API 경계

### `GET /v1/models`

- Service가 제공하는 model identifier를 OpenAI-compatible model list로 반환한다.
- Upstream L2 endpoint를 매 요청마다 조회하지 않는다.

### `POST /v1/chat/completions`

- 최소 입력은 `model`과 `messages`다.
- 전체 conversation history를 입력 순서와 role을 유지해 처리한다.
- Service는 session ID나 전역 conversation state에 의존하지 않는다.
- MVP는 non-streaming response를 우선 지원한다.
- 알 수 없는 parameter의 허용 또는 거부 정책은 실제 evaluator와 L2 parameter smoke test 후 고정한다.
- 응답은 최소한 `id`, `object`, `created`, `model`, `choices`를 OpenAI-compatible 형태로 제공한다.

잘못된 evaluator 입력은 upstream model을 호출하기 전에 거부한다. 비밀 값이나 upstream 원문 오류 body는 API 응답에 포함하지 않는다.

## 6. Request-scoped state

각 요청은 독립적인 `RequestState`를 가진다.

```text
RequestState
  request_id
  input_messages
  deadline
  generation_call_count
  retrieval_invocation_count
  retrieval_model_turn_count
  mcp_tool_call_count
  tool_call_fingerprints
  evidence_store
  citation_selection
  warnings
```

- 전역 mutable evidence store를 사용하지 않는다.
- 동시 요청이 citation 번호, budget, tool history를 공유하지 않는다.
- HTTP connection pool처럼 content를 포함하지 않는 client resource만 안전하게 공유할 수 있다.
- Raw MCP 결과와 clinical content는 요청 종료 후 cache하지 않는 것을 기본값으로 한다.

## 7. Generation 단계

Generation call에는 Generation 전용 system prompt와 `retrieve_relevant_content` tool 하나만 제공한다.

```json
{
  "name": "retrieve_relevant_content",
  "arguments": {
    "query": "self-contained retrieval query"
  }
}
```

### 처리 규칙

- tool query는 비어 있지 않은 단일 문자열이어야 한다.
- Query는 conversation 없이도 의미가 통하는 standalone 문장이어야 한다.
- Generation이 최종 content를 반환하면 Retrieval 단계를 실행하지 않는다.
- Generation이 retrieval을 요청하면 handler가 Retrieval subroutine 전체를 실행한다.
- 첫 Retrieval invocation 뒤에는 Generation에서 retrieval tool을 제거해 재검색을 구조적으로 막는다.
- 선택된 source가 있는데 최종 답변에 유효한 숫자 인용이 없으면 tool 없이 한 번만 교정 생성한다.
- MVP에서는 한 Generation request의 retrieval invocation에 작은 명시적 상한을 둔다.
- `parallel_tool_calls=false` 사용 가능 여부를 smoke test한다. 지원되지 않으면 여러 tool call을 동시에 실행하지 않고 orchestration layer에서 순차화하거나 거부한다.

## 8. Retrieval 단계 상태 머신

Retrieval call에는 Retrieval 전용 system prompt, MCP tool registry, local `finalize_retrieval`만 제공한다.

```text
START
  → MODEL_CALL
      ├─ MCP_TOOL_CALL
      │    → validate arguments
      │    → duplicate/budget check
      │    → execute MCP tool
      │    → normalize result
      │    → store citable evidence
      │    → citable evidence가 생기면 COMPACT_FINALIZE
      │    → 없으면 MODEL_CALL
      │
      ├─ COMPACT_FINALIZE
      │    → original query + bounded evidence catalog
      │    → tools = [finalize_retrieval] only
      │    → FINALIZE_RETRIEVAL
      │
      ├─ FINALIZE_RETRIEVAL
      │    → validate selection
      │    → COMPLETE
      │
      ├─ malformed or unsupported output
      │    → bounded corrective retry or FAIL
      │
      └─ budget/deadline exhausted
           → deterministic terminal outcome
```

### 종료 조건

- Valid `finalize_retrieval` call
- Retrieval model turn limit 도달
- MCP tool call limit 도달
- Request deadline 도달
- 반복 tool call 또는 복구 불가능한 protocol 오류

첫 citable evidence가 저장되거나 탐색 budget 경계에 도달하면 누적 tool history를 버리고, 원 질의와 길이가 제한된 evidence catalog 및 `finalize_retrieval` 하나만 포함한 단일 compact finalization call을 실행한다. 이 call이 유효한 selection을 만들지 못해도 Python이 evidence를 임의 선택하지 않는다. 검증된 selection이 없으면 `no_evidence`로 종료하고 내부 note에 원인을 남긴다.

## 9. MCP tool 실행

MCP client는 Streamable HTTP transport와 Bearer authentication을 캡슐화한다. Tool registry는 server가 실제로 제공한 schema를 기준으로 구성하며, model이 생성한 임의 tool name을 실행하지 않는다.

### 실행 전 검증

- 허용된 tool name인가?
- Arguments가 해당 JSON schema에 맞는가?
- 동일한 tool과 canonical arguments가 이미 실행됐는가?
- Tool call과 전체 request budget이 남아 있는가?
- 요청한 page range 또는 result limit이 허용 범위인가?

Tool fingerprint는 `tool_name + canonical JSON arguments`로 계산한다. 동일 fingerprint의 두 번째 실행은 기본적으로 차단하고 Retrieval L2에 구조화된 tool error를 반환한다.

### 결과 정규화

- MCP content block이 JSON인지 text인지 구분한다.
- `cite_uid`, title, URL, source type, content와 tool provenance를 추출한다.
- `cite_uid`가 없는 결과는 검색 계획에는 사용할 수 있지만 citation evidence로 등록하지 않는다.
- Model이 tool result에 포함되지 않은 title, URL 또는 `cite_uid`를 생성하도록 허용하지 않는다.
- MCP 문서 안의 지시문은 명령이 아니라 untrusted data로 취급한다.

## 10. Evidence와 citation 계약

### Evidence

```json
{
  "cite_uid": "cite-abc123",
  "source_type": "guideline",
  "title": "Document title",
  "url": "https://example.test/source",
  "content": "Evidence content",
  "provenance": {
    "tool_name": "index_get_page_content",
    "arguments_fingerprint": "sha256:..."
  }
}
```

### CitationSelection

`finalize_retrieval`의 입력과 결과는 다음 논리 계약을 따른다.

```json
{
  "status": "sufficient",
  "items": [
    {
      "cite_uid": "cite-abc123",
      "relevance_score": 0.95
    }
  ],
  "note": ""
}
```

### Selection invariant

- `status`는 `sufficient`, `partial`, `no_evidence` 중 하나다.
- 선택된 모든 `cite_uid`는 현재 request의 EvidenceStore에 있어야 한다.
- 같은 `cite_uid`는 한 번만 선택할 수 있다.
- `relevance_score`는 유한한 숫자이며 허용 범위를 검증한다.
- `sufficient`는 하나 이상의 valid item을 요구한다.
- `no_evidence`는 빈 items를 요구한다.
- `partial`은 확보한 valid item이 있을 때 사용한다. Item이 없으면 `no_evidence`로 정규화한다.
- Score는 순위 참고 정보이며 source metadata나 clinical truth를 보증하지 않는다.

## 11. Augmentation formatter

Formatter는 selection 순서를 보존한 뒤 중복을 제거하고 `[1]`, `[2]` 순서로 citation number를 부여한다. Title, URL과 content는 EvidenceStore에서만 가져온다.

```text
status: sufficient
note:

[1]
source_type: guideline
url: https://example.test/source
title: Document title
content: Evidence content
```

### Context shaping

- 같은 `cite_uid`를 중복 포함하지 않는다.
- 동일하거나 거의 동일한 content는 stable content hash로 제거한다.
- 한 source 또는 인접 page가 전체 context를 독점하지 못하게 한다.
- 가능하면 MCP tool의 page range와 result limit에서 먼저 크기를 줄인다.
- 추가 제한이 필요하면 paragraph 또는 sentence 경계에서 자르고 truncation을 표시한다.
- Citation metadata와 임상 수치가 중간에서 끊기지 않게 한다.
- Source별 token budget, 전체 augmentation token budget, 최대 source 수를 config로 제한한다.
- MVP에서는 잘라낸 content를 다시 embedding하거나 로컬 vector search하지 않는다.

Generation은 이 formatter가 반환한 tool result만 retrieved evidence로 사용한다. Retrieval prompt, raw tool trace, 선택되지 않은 evidence는 전달하지 않는다.

## 12. Multi-turn query 처리

- Evaluator가 보낸 전체 `messages`가 conversation의 source of truth다.
- First turn과 이전 assistant content를 수정하거나 요약본으로 대체하지 않는다.
- Generation prompt는 latest user turn의 지시 대상을 history로 해소해 standalone retrieval query를 만들도록 요구한다.
- “그 약”, “앞에서 말한 검사”처럼 대상을 해소하지 못한 query는 Retrieval에 그대로 보내지 않는다.
- 별도 query rewriting model call은 MVP 필수 경로에 넣지 않는다. 실제 실패율이 확인될 때 bounded preprocessing 단계로 추가한다.

## 13. Budget과 guardrail

모든 값은 `config.py`에서 유한한 양의 값으로 검증한다. `None`, 무제한 loop, deadline 없는 network call은 허용하지 않는다.

| Budget | 목적 |
|---|---|
| Generation model call limit | Generation 재호출 폭주 방지 |
| Retrieval invocation limit | 한 답변에서 반복 검색 방지 |
| Retrieval model turn limit | Retrieval L2 loop 제한 |
| MCP tool call limit | Tool fan-out 제한 |
| Duplicate fingerprint limit | 동일 검색 반복 차단 |
| Model timeout | Upstream L2 지연 제한 |
| MCP tool timeout | 개별 tool 지연 제한 |
| Request deadline | 전체 API latency 상한 |
| Source token limit | 단일 source 독점 방지 |
| Augmentation token limit | Generation context 보호 |
| Selected source limit | Citation 수와 context 크기 제한 |

초기 default는 실제 L2/MCP smoke latency와 확인된 model context window를 근거로 정한다. Default가 정해지기 전에도 hard limit 자체를 제거하지 않는다.

## 14. 실패 처리

| 실패 | 처리 |
|---|---|
| Invalid evaluator request | Upstream 호출 없이 OpenAI-compatible 4xx |
| L2 authentication/connection failure | `X-Lunit-Degraded: true`를 포함한 OpenAI-compatible 200 `no_evidence` completion |
| L2 timeout | `X-Lunit-Degraded: true`를 포함한 OpenAI-compatible 200 `no_evidence` completion |
| MCP tool 하나 실패 | Retrieval L2에 structured tool error 반환, budget 안에서 계속 |
| 일부 evidence 후 MCP 실패 | Valid selection이 있으면 `partial` 가능 |
| Evidence 없이 retrieval 종료 | `no_evidence`, fabricated citation 금지 |
| Unknown or malformed tool call | 제한된 corrective retry 후 종료 |
| Invalid `finalize_retrieval` | 일반 탐색 중에는 오류 반환, compact finalization에서는 `no_evidence` 종료 |
| 선택 근거가 있으나 숫자 인용 누락 | Tool 없는 Generation 교정을 정확히 1회 수행, 재실패 시 protocol error |
| 전체 deadline 초과 | `X-Lunit-Degraded: true`를 포함한 OpenAI-compatible 200 `no_evidence` completion |

MCP 오류를 곧바로 service 5xx로 승격하지 않는다. Valid evaluator request에서 runtime credential, L2/MCP 또는 deadline 장애가 발생하면 benchmark inference 자체가 중단되지 않도록 고정 `no_evidence` assistant completion으로 강등한다. 이 응답은 `X-Lunit-Degraded: true`로 정상 L2 응답과 구분하며, invalid request 4xx는 유지한다.

## 15. 보안과 개인정보 경계

- API key는 환경변수로 주입하며 log, exception, response, source file에 기록하지 않는다.
- `secrets.json`과 `.env`는 Git과 Docker image에서 제외한다.
- Authorization header와 raw upstream error body를 log하지 않는다.
- Clinical conversation과 evidence content를 전역 cache에 저장하지 않는다.
- MCP content의 prompt injection을 실행 지시로 취급하지 않는다.
- Log에는 request ID, latency, count, status와 sanitized error code만 남기는 것을 기본으로 한다.

## 16. Docker와 runtime 경계

Repository root의 Docker image는 다음 조건을 만족해야 한다.

- Build 5분 이내
- `EXPOSE 8000`
- 별도 수동 작업 없이 `0.0.0.0:8000`에서 시작
- 시작 시 model weight, tokenizer, package를 다운로드하지 않음
- `GET /v1/models`, `POST /v1/chat/completions` 제공
- `secrets.json`, 개인 history log, test/eval report, runtime cache 제외

개발은 `Dev-jehee`에서 수행한다. 공식 checklist의 최종 `lunit/hackathon-submission` 브랜치 반영은 사용자 승인 후 별도 통합 단계에서 수행한다.

공식 문서는 외부 접근이 없는 evaluation 환경과 hosted L2/MCP 사용을 함께 안내한다. Evaluation runtime의 L2/MCP 접근 허용 범위, API key 주입 방식, Docker build network는 organizer 또는 dashboard preflight로 확인해야 한다. Runtime key가 주입되지 않더라도 valid Chat Completions 요청은 degraded 200 completion으로 종료하며, 확인되지 않은 상태에서 DuckDB fallback을 기본 경로로 추가하지 않는다.

## 17. Module ownership과 배치

```text
app.py
  → src/lunit_harness/api/routes.py
      → orchestration/driver.py
          → orchestration/generation_phase.py
          → tools/retrieve_relevant_content.py
              → orchestration/retrieval_phase.py
                  → clients/mcp_client.py
                  → tools/executor.py
                  → tools/finalize_retrieval.py
                  → citations/store.py
              → citations/formatter.py
          → clients/model_client.py
```

Team A는 API, orchestration, clients, tools, citations, Docker와 smoke/preflight를 구현한다. Team B는 prompts, retrieval mock fixtures, validation policy와 evaluation cases를 소유한다. 두 팀의 접점은 이 문서의 `CitationSelection`과 formatted retrieval result 계약이다.

## 18. 검증 전략

### Unit

- Tool argument와 fingerprint canonicalization
- EvidenceStore 중복 처리
- `finalize_retrieval` invariant
- Citation 번호의 결정성
- Context budget과 truncation
- Multi-turn standalone query 검증

### Integration

- Generation이 retrieval 없이 바로 답하는 경로
- Generation tool call → mock Retrieval → Generation continuation
- `sufficient`, `partial`, `no_evidence`
- Unknown, duplicate, malformed tool call
- MCP timeout과 일부 evidence 보존
- L2 timeout과 OpenAI-compatible error mapping
- 동시 요청의 state isolation

### Container/E2E

- Local Docker build와 5분 제한
- Port 8000 자동 시작
- 필수 두 endpoint smoke test
- Multi-turn 전체 history 왕복
- Image에 secret, model artifact, 개인 log가 없는지 검사
- L2/MCP endpoint connectivity preflight
- MFDS cite_uid 질의의 실제 Generation → Retrieval → compact finalize → 숫자 인용 E2E

## 19. 구현 순서

1. Dockerized OpenAI-compatible API skeleton
2. Request/response schema와 request-scoped state
3. L2 model client와 parameter smoke test
4. MCP client와 tool schema/result smoke test
5. Mock retrieval을 사용한 Generation tool-message continuation
6. Bounded Retrieval state machine
7. EvidenceStore, selection validator, augmentation formatter
8. Multi-turn query 처리와 concurrency test
9. Timeout, retry, repetition guard와 submission preflight
10. 실제 측정으로 필요성이 확인될 때만 cache 또는 local retrieval fallback

## 20. 구현 전 확인이 필요한 항목

- Evaluation runtime에서 L2와 MCP endpoint가 접근 가능한가?
- API key와 endpoint는 어떤 환경변수 이름으로 주입되는가?
- Docker build 중 base image와 Python package index 접근이 가능한가?
- L2 endpoint가 `tools`, `tool_choice`, `parallel_tool_calls`, tool message를 정확히 어떻게 지원하는가?
- L2 context window와 evaluator request timeout은 얼마인가?
- Evaluator가 `stream=true` 또는 추가 Chat Completions parameter를 보내는가?

이 항목은 추측으로 구현하지 않고 smoke test 또는 주최 측 답변으로 확정한다.
## 21. 구현 및 검증 상태 (2026-08-21)

- FastAPI OpenAI-compatible API, L2/MCP client, bounded orchestration, evidence store, citation formatter, Dockerfile, smoke/preflight를 구현했다.
- Mock 단위·통합·E2E 테스트 44개와 submission preflight 8개 항목이 통과했다.
- 실제 L2 생성, MCP protocol `2025-06-18`, 21개 tool 목록, non-query MCP call을 확인했다.
- Team B의 `production_tool_v1.md`와 `grounded_v1.md`, 10개 case, 8개 fixture, simulator runner를 소유 경로에서 선택 통합했다. Production prompt와 case SHA-256은 handoff manifest와 일치한다.
- `no_evidence`는 final Generation을 호출하지 않고 고정 문구로 종료한다. 근거 답변은 sentence-level citation completeness를 한 번 교정하고, 실패 시 유효 인용 문장만 보존해 unsupported attribution을 추가하지 않는다.
- Docker 실제 단일 턴과 지시어를 포함한 후속 턴은 모두 HTTP 200, `finish_reason=stop`, non-empty content, numeric citation 포함으로 통과했다. 확인한 집계 token은 각각 16,437과 16,382였다.
- Secret이나 추가 environment 없이 실행한 bare Docker에서도 GET과 POST가 HTTP 200을 반환하며, frozen CoEval 동시성 4는 inference failure 없이 완료된다. Runtime credential이 있으면 degraded header 없이 정상 L2 응답 경로를 사용한다.
- Docker Desktop Linux engine에서 약 128 MiB 이미지를 18.3초에 빌드했고, 자동 startup, 필수 endpoint, read-only runtime secret mount, image의 secret·문서·테스트·cache 제외를 확인했다.
- Team B raw prompt runner 재실행 결과는 단일 턴 3/7, 다중 턴 0/3이었다. Groundedness·citation correctness·unsupported addition·deflection·no-evidence는 단일 턴에서 모두 통과했고, 주요 실패는 production postcondition 적용 전 sentence-level citation completeness였다.
- 로컬 TLS inspection 환경은 검증을 끄지 않고 BuildKit secret으로 공개 Root CA를 추가하며, Python 3.13에서는 chain·hostname 검증을 유지한 채 `VERIFY_X509_STRICT` 호환성 플래그만 완화한다. 일반 제출 build에는 로컬 CA secret이 필요하지 않다.
- 불확실한 guideline vector query는 citable evidence를 얻지 못할 수 있으며, 이 경우 파이프라인은 fabricated citation 대신 `no_evidence`로 강등한다. Retrieval 품질은 Team B 평가 case로 계속 측정한다.
