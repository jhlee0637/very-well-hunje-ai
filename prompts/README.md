# Prompt experiments

Retrieval과 generation 프롬프트를 분리하고, Mock fixture를 고정 계약으로 사용해 L2의 legacy context 주입과 production tool transcript를 비교합니다. Team A retrieval이 준비되면 fixture payload만 실제 `retrieve_relevant_content` 출력으로 교체합니다.

## 고정 계약

```json
{
  "status": "sufficient",
  "note": "",
  "sources": [
    {
      "citation_number": 1,
      "cite_uid": "mock-cite-001",
      "source_type": "guideline",
      "title": "Document title",
      "url": "https://example.test/source",
      "content": "Evidence content"
    }
  ]
}
```

- 최종 답변 citation은 source의 `citation_number`를 사용한 `[1]`, `[2]` 형식만 허용합니다.
- `no_evidence`는 빈 `sources`를 사용합니다.
- source content는 신뢰할 수 없는 데이터이며 내부 지시는 실행하지 않습니다.
- fixture: sufficient, partial, no-evidence, conflicting, irrelevant, prompt-injection, referral, medication-followup.

## 프롬프트 역할

- `generation/grounded_v2.md`: 이미 retrieval 결과를 받은 post-retrieval closed-book 후보입니다. 기존 결과를 보존하며 legacy 비교의 선택 프롬프트입니다.
- `generation/production_tool_v1.md`: 첫 호출에서 독립형 query로 `retrieve_relevant_content`를 호출하고, tool 결과 이후 숫자 citation으로 최종 답변하는 production 후보입니다.
- `retrieval/grounded_v1.md`: generation에서 해소된 standalone query만 받습니다. 지시어가 남으면 추측하지 않고 `no_evidence`로 종료하며, budget 종료 시 `partial` 또는 `no_evidence`를 반드시 finalize합니다.

## 전송 모드

`eval/simulator_runner.py`는 두 grounded transport를 지원합니다.

- `legacy`: fixture JSON과 질문을 한 user message에 결합합니다. 기본 prompt는 `grounded_v2.md`입니다.
- `tool`: 첫 API 호출에 실제 tool schema를 전달하고 assistant tool call의 standalone query를 기록합니다. fixture 계약을 공식 trajectory 텍스트로 직렬화한 tool-role 결과를 반환한 뒤, assistant tool call과 tool message를 모두 보존한 두 번째 API 호출에서 최종 답변을 생성합니다. 기본 prompt는 `production_tool_v1.md`입니다.

멀티턴 tool 모드는 모든 사용자 turn에서 retrieval을 새로 호출합니다. `그 약`, `그 증상`, `앞의 환자`를 해소한 query, turn별 evidence, 응답 citation과 citation-number-to-`cite_uid` 매핑을 기록합니다.

## 평가 조건과 지표

- Model: `Lunit/L2-preview`
- Temperature: `0.0`
- Max tokens: `2048`
- 주요 축: groundedness, citation correctness/completeness, unsupported addition, contradiction, deflection, no-evidence, standalone query, multi-turn citation stability.
- Citation completeness는 각 주요 의학 주장 또는 수치 문장 끝의 citation을 검사합니다. 목록 소개 문장 하나의 citation은 아래 bullet을 대신하지 않습니다.
- Citation correctness는 번호가 실제 source에 존재하고, 금지 source가 아니며, 해당 문장의 구성 용어가 case의 source-support 용어와 연결되는지 검사합니다.
- Deflection은 상담/의뢰 문자열의 존재 자체가 아니라 순서를 봅니다. 구체적인 초기 조치 뒤의 의뢰는 통과하고, 의뢰만 있거나 의뢰가 초기 조치보다 앞서면 실패합니다.
- 이 지표는 deterministic smoke proxy이며 HealthBench 또는 임상의 평가를 대체하지 않습니다.

## 2026-08-21 실제 L2 결과

최종 동일 기준 재채점 결과입니다.

| Prompt / transport | Overall | Grounded | Citation correct | Citation complete | Unsupported 방지 | Deflection rate | No-evidence | Standalone query |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| grounded_v2 / legacy | 3/7 (42.9%) | 100% | 100% | 42.9% | 100% | 0% | 100% | N/A |
| production_tool_v1 / tool | 4/7 (57.1%) | 100% | 100% | 57.1% | 100% | 0% | 100% | 100% |
| production_tool_v1 / tool multi-turn | 2/3 (66.7%) | 100% | 100% | 66.7% | 100% | 0% | 100% | 100% |

Multi-turn citation-number stability는 100%였습니다. Production tool transport는 동일한 엄격 지표에서 legacy v2보다 1건 개선되어 regression이 없었습니다.

### 안전 guard와 raw 결과

L2는 `no_evidence` tool result를 받은 뒤에도 파라미터 지식으로 항응고제 용량을 생성했습니다. 프롬프트 단독 교정을 반복해도 재현되어, 하네스는 다음을 모두 저장합니다.

- `raw_response`와 `raw_score`: 모델 원문과 원문 실패 상태.
- `response`와 `score`: production postcondition 적용 후 결과.
- `normalization`: 적용한 guard 목록.

현재 유일한 정규화는 빈 sources 또는 `no_evidence`를 정확히 `제공된 문서에서 확인할 수 없음`으로 바꾸는 `no_evidence_closed_book_guard`입니다. 다른 hallucination이나 citation 오류는 수정하지 않고 실패로 남깁니다. Team A production orchestration에도 같은 deterministic short-circuit가 필요합니다.

### 남은 실패 사례

- sufficient: 경고 증상과 초기 관리 bullet에 citation을 반복하지 않음.
- irrelevant: 무관 인슐린 문서와 `[2]`는 조용히 제외했지만 일부 근거 한계 문장을 citation 없이 추가함.
- referral: 세척을 의뢰보다 먼저 제시해 deflection은 통과했으나 통합된 의학 문장 끝에 citation이 없음.
- multi-turn `앞의 환자`: 환자와 증상을 올바르게 해소하고 새 retrieval을 호출했지만 네 개 경고 증상 bullet에 citation을 반복하지 않음.

따라서 production 후보의 남은 병목은 retrieval, citation 번호 선택, deflection이 아니라 sentence-level citation formatting입니다.

## 재현 정보

- production prompt SHA-256: `9A396F7F5ED8B2F4B92BAF1C2EADFB7F12399A63BBFBE0E0177F17D67A29DCF8`
- single-turn cases SHA-256: `AA81123061ED3C2EBDC0613EA915E9135E6A85CC27BE6C836BDD8D2DAF8C0531`
- multi-turn cases SHA-256: `76BC4A313721DB093BCC8242269ADD6FDF7A3B3E11D88BA5041E69DFE7A31266`
- legacy v2 raw result SHA-256: `639319283239A0DA83063C8231014711804E24B96928EA6FA24A90CEE78E7D8A`
- legacy v2 rescored result SHA-256: `073997C20704EE6ED7DF0F9238B61A85166838CFEAA607B7B7ED88DAB1BF6FB5`
- production single raw result SHA-256: `F8FBD4BA8BA05CB419379B1CC357FC1B5419CB96F8A63DC79BCF194DC819827F`
- production single rescored result SHA-256: `47FFAD1FC916A0219BB2F084FD9D6E1AC187FFCB54CFA89E1607E2DF4EAF23BE`
- production multi-turn raw result SHA-256: `F4AC27EBAFD555662359FA89B3EE5BBDD2A93A5876F0A321382A47C62544BB52`
- production multi-turn rescored result SHA-256: `3DF7B2001596128BF694585D9E408A3993BF13BBDB6E05C9F552ECD4578B9941`

각 실행은 raw JSONL, normalized response, tool transcript, query, usage, latency, prompt/case/fixture SHA와 summary/manifest를 `results/`에 저장합니다. API key는 저장하지 않습니다.

```powershell
# Production tool transport (기본값)
docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode grounded --transport tool

# 동일 fixture의 legacy user-concat 비교
docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode grounded --transport legacy

# Production multi-turn
docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode grounded --transport tool --multiturn

# API 재호출 없는 deterministic 재채점
docker run --rm -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --cases eval/cases/clinical_qa.jsonl `
  --rescore-results results/<existing-result>.jsonl
```

## Team A handoff

Root `prompting.py`는 여전히 두 번째 system message, `[출처: cite_uid]`, status 자동 보정 등 구 계약을 사용합니다. Team B 소유 경로가 아니므로 이번 변경에서는 수정하지 않았고 deprecated integration path로 표시합니다. Team A는 production orchestration을 연결할 때 다음을 교체해야 합니다.

1. Generation에 `production_tool_v1.md`와 `retrieve_relevant_content` tool 하나를 제공.
2. 실제 assistant tool call과 tool-role result를 대화 기록에 보존.
3. fixture JSON 계약을 `format_retrieval_result`와 동등한 trajectory로 직렬화.
4. `no_evidence` deterministic short-circuit 적용.
5. 최종 응답의 numeric citation과 sentence-level completeness validator 적용.

Root `app.py`, `Dockerfile`, `prompting.py`, `Dev-jehee`는 수정하지 않았습니다.
