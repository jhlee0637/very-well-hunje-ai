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
- `generation/production_tool_v1.md`: 모든 사용자 질문에 retrieval을 강제했던 보존용 baseline입니다.
- `generation/production_tool_v2.md`: 일반 의료·비의료 질문은 직접 답하고 특정 근거·정밀 수치·희귀/비전형 사례만 독립형 query로 retrieval하는 production 후보입니다. Tool 결과 이후 숫자 citation과 closed-book 규칙은 유지합니다.
- `generation/production_tool_v3.md`: v2의 조건부 routing을 간결화하고, 직접 답변을 기본값으로 명시한 token-budget 기준 후보입니다. 명백한 일반·고수준 요청은 코드 게이트에서도 tool을 숨깁니다.
- `generation/production_tool_v4.md`: HealthBench 품질 정합 후보입니다. 환자·보호자·임상의를 동적으로 구분하고 사용자 언어를 따르며, 임상적 정확성·완전성·맥락·소통을 token 최소화나 citation 형식보다 우선합니다. 검색 실패 시에도 검증되지 않은 정밀 사실은 만들지 않으면서 고신뢰 안전 조치와 필요한 확인 정보를 보존합니다.
- `retrieval/grounded_v1.md`: generation에서 해소된 standalone query만 받습니다. 지시어가 남으면 추측하지 않고 `no_evidence`로 종료하며, budget 종료 시 `partial` 또는 `no_evidence`를 반드시 finalize합니다.

## 전송 모드

`eval/simulator_runner.py`는 두 grounded transport를 지원합니다.

- `legacy`: fixture JSON과 질문을 한 user message에 결합합니다. 기본 prompt는 `grounded_v2.md`입니다.
- `tool`: 첫 API 호출에 실제 tool schema를 전달하고 assistant의 direct answer 또는 standalone retrieval query를 기록합니다. Retrieval을 호출한 경우 fixture 계약을 공식 trajectory 텍스트로 직렬화한 tool-role 결과를 반환한 뒤, assistant tool call과 tool message를 모두 보존한 두 번째 API 호출에서 최종 답변을 생성합니다. 평가 러너의 기본 prompt는 품질 A/B에서 선택된 `production_tool_v4.md`입니다.

멀티턴 tool 모드는 모든 사용자 turn에서 retrieval을 새로 호출합니다. `그 약`, `그 증상`, `앞의 환자`를 해소한 query, turn별 evidence, 응답 citation과 citation-number-to-`cite_uid` 매핑을 기록합니다.

## 평가 조건과 지표

- Model: `Lunit/L2-preview`
- Temperature: `0.0`
- Max tokens: `2048` (retrieval `512`, citation repair `768`)
- 주요 축: groundedness, citation correctness/completeness, unsupported addition, contradiction, deflection, no-evidence, standalone query, multi-turn citation stability.
- Citation completeness는 각 주요 의학 주장 또는 수치 문장 끝의 citation을 검사합니다. 목록 소개 문장 하나의 citation은 아래 bullet을 대신하지 않습니다.
- Citation correctness는 번호가 실제 source에 존재하고, 금지 source가 아니며, 해당 문장의 구성 용어가 case의 source-support 용어와 연결되는지 검사합니다.
- Deflection은 상담/의뢰 문자열의 존재 자체가 아니라 순서를 봅니다. 구체적인 초기 조치 뒤의 의뢰는 통과하고, 의뢰만 있거나 의뢰가 초기 조치보다 앞서면 실패합니다.
- 이 지표는 deterministic smoke proxy이며 HealthBench 또는 임상의 평가를 대체하지 않습니다.

## Quality-first 목표와 독립 평가

Trial 5의 공식 9.60 이후 최적화 목표를 다음처럼 수정했습니다.

1. 1차 목표: HealthBench형 weighted clinical rubric의 accuracy와 completeness.
2. 2차 목표: patient/guardian/clinician persona와 다국어·multi-turn context awareness.
3. 안전 제약: harmful advice, unsupported exact dose·regulatory fact, prompt injection 방지.
4. 운영 제약: token budget은 무한 loop를 막는 상한이며 임상적으로 필요한 내용을 삭제하는 목표가 아님.

새 평가 자산:

- `eval/cases/quality_qa.jsonl`: 원본 single-turn 17건, quality rubric 83개.
- `eval/cases/quality_multiturn.jsonl`: 위험도가 후속 turn에서 변하는 원본 multi-turn 5건.
- axis: `accuracy`, `completeness`, `context_awareness`, `communication_quality`, `instruction_following`.
- positive point와 penalty point를 HealthBench와 같은 가중식으로 합산하는 deterministic proxy.

이 케이스는 공개 HealthBench 문항이나 hidden validation을 복제하지 않고 새로 작성했습니다. Regex rubric은 빠른 회귀 검출용이며 physician rubric 또는 LLM judge를 대체하지 않습니다. 내용 기준이 비어 있는 route holdout과 달리 모든 quality case는 다수의 임상 내용 기준을 가져야 합니다.

```powershell
# tool 없는 quality baseline: 프롬프트 자체의 임상 답변 품질 비교
python eval/simulator_runner.py --mode baseline `
  --prompt prompts/generation/production_tool_v4.md `
  --cases eval/cases/quality_qa.jsonl

# multi-turn context escalation
python eval/simulator_runner.py --mode baseline --multiturn `
  --prompt prompts/generation/production_tool_v4.md `
  --cases eval/cases/quality_multiturn.jsonl
```

Team A의 `c617ea7` orchestration과 통합해 helpful no-evidence, bounded retrieval, compact citation repair, dynamic persona/language 계약을 production 경로에 연결합니다. Citation validator의 deterministic safety 경계는 유지하고 별도 회귀로 비파괴 정책을 검증합니다.

### 2026-08-22 quality A/B 결과

동일한 `Lunit/L2-preview`, temperature `0.0`, max tokens `2048` 조건에서 v2와 v4를 비교했습니다. 아래 결과는 공식 dashboard 점수가 아니라 공개 benchmark를 복제하지 않은 원본 deterministic proxy입니다.

| 평가 | Prompt | 통과 | 평균 quality rubric | 평균 지연 | 평균 응답 문자 | 총 token |
|---|---|---:|---:|---:|---:|---:|
| single-turn 17건 | v2 | 5/17 (29.4%) | 0.4024 | 16.810초 | 650.8 | 43,896 |
| single-turn 17건 | v4 | 12/17 (70.6%) | 0.7552 | 17.269초 | 1,105.2 | 47,211 |
| multi-turn 5건 | v2 | 4/5 (80.0%) | 0.8121 | 28.604초 | 856.8 | 31,952 |
| multi-turn 5건 | v4 | 5/5 (100%) | 1.0000 | 45.018초 | 1,142.4 | 35,603 |

v4는 single-turn quality를 `+0.3528`, multi-turn quality를 `+0.1879` 높였습니다. 총 token 증가는 각각 7.6%, 11.4%였습니다. 특히 multi-turn context-awareness는 0.75에서 1.00으로 상승했습니다. 따라서 현재 선택 후보는 v4이며, 응답 길이 증가는 임상 내용 누락을 줄이기 위한 허용 가능한 비용으로 판단합니다. 공식 Trial 5의 대규모 token 사용은 이 소규모 A/B의 증가율로 설명되지 않으므로, Team A 통합 후 tool 반복 호출·누적 transcript·검색 payload 크기를 별도로 계측해야 합니다.

루브릭은 안전한 부정문을 위험 권고로 오인하지 않고 `숨을 쉬는지 확인`처럼 의미가 같은 한국어 표현을 인정하도록 회귀 테스트를 추가했습니다. 출력 문구를 정답 문자열에 맞추는 방식은 사용하지 않았습니다.

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

이 2026-08-21 평가 당시 유일한 정규화는 빈 sources 또는 `no_evidence`를 정확히 `제공된 문서에서 확인할 수 없음`으로 바꾸는 `no_evidence_closed_book_guard`였습니다. 이후 production 통합에서는 한 줄 고정 응답 대신 확인 불가 범위·안전 원칙·검증 단계가 있는 helpful no-evidence 응답과 unsupported exact fact guard를 사용합니다.

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

## Team A handoff (2026-08-21 당시 기록)

당시 root `prompting.py`는 두 번째 system message, `[출처: cite_uid]`, status 자동 보정 등 구 계약을 사용했습니다. 이후 Team A `c617ea7` 통합에서 이 deprecated 경로는 제거되고 production orchestration으로 교체되었습니다. 아래 목록은 당시의 handoff 요구사항입니다.

1. Generation에 `production_tool_v1.md`와 `retrieve_relevant_content` tool 하나를 제공.
2. 실제 assistant tool call과 tool-role result를 대화 기록에 보존.
3. fixture JSON 계약을 `format_retrieval_result`와 동등한 trajectory로 직렬화.
4. `no_evidence` deterministic short-circuit 적용.
5. 최종 응답의 numeric citation과 sentence-level completeness validator 적용.

위 2026-08-21 handoff 당시에는 root `app.py`, `Dockerfile`, `prompting.py`, `Dev-jehee`를 수정하지 않았습니다.

## 2026-08-22 production_tool_v2 targeted smoke

모든 질문에 retrieval을 강제하던 v1에서 조건부 routing v2로 전환했습니다. 일반 의료 질문은 direct로, 특정 근거·정밀 수치·환자별 임상 결정은 retrieval로 처리하며, tool 직후 citation formatting reminder와 production과 동일한 1회 repair/fallback을 평가 러너에도 적용했습니다.

- 대표 fixture-backed case: 단일 9/9, multi-turn 3/3, 합계 12/12
- Direct API smoke: 5.72초, 2,305 tokens, degraded 없음, citation 없음
- Retrieval API smoke: 49.62초, 19,977 tokens, degraded 없음, 숫자 citation 존재
- Prompt SHA-256: `195B853F274FC3B1C7DADCEFDBEAD31C273680919AC96E350DCDCD4C54882765`
- Single-turn cases SHA-256: `512FF207367EC9A7FA7B58BEF365846914455438A7187E5B1F875DCD4702FD02`
- Multi-turn cases SHA-256: `6459746F1185EFCFBFC79DC99A5991EC5A71B7290488A2B28F5D5ACA88292DCA`

이 결과는 동일 prompt/case의 로컬 L2·fixture targeted smoke이며 공식 dashboard 점수가 아닙니다. 복합 MFDS 적응증+금기 live 질의는 한 evidence round에서 적응증만 확보해 금기 범위를 누락했으므로, 관찰상 이득 없이 `no_evidence`를 늘린 다중 evidence round는 production 기본값으로 채택하지 않았습니다.

## 2026-08-22 production_tool_v3 token-budget holdout

Trial 4의 4.05점과 17.5M tokens(input 16.7M / output 860.4K)를 기준으로, 모든 turn retrieval·전체 MCP schema 재전송·raw tool history 누적을 분리해 수정했습니다. Holdout은 prompt에 포함되지 않은 20개 질문으로 direct/retrieval을 10개씩 균형 구성했으며, 불완전한 지시어 대신 실제 검색 가능한 개체를 포함합니다.

| 지표 | 결과 |
|---|---:|
| 전체 / routing | 20/20 / 20/20 |
| Groundedness / citation correctness / completeness | 100% / 100% / 100% |
| Unsupported addition / contradiction / deflection | 100% / 100% / 0% deflection rate |
| no-evidence | 100% |
| 총 token | 35,390 (input 28,240 / output 7,150) |
| Direct / retrieval 평균 token | 1,972.9 / 1,566.1 |
| 평균 latency | 4.905초 |

- Prompt SHA-256: `3FB4E18385ADCA092BEDB0C88D3294988F1E4087BECDA11ED3F217DED51724C3`
- Holdout cases SHA-256: `B5E6BD17DBF9CF7380B98E109ED464BEE92B5280DD4DFD58FAF8FE1C0D88107D`
- Result SHA-256: `3642FDE2A157A77D5142D842AF2955BDAAA855E4908A37BBF08210B2387383C1`
- 최종 Docker direct smoke: 2,212 tokens, 12.11초, `finish_reason=stop`.
- 실제 MFDS retrieval smoke: 8,234 tokens, 24.18초, 숫자 citation 존재. v2의 19,977 tokens보다 58.8% 적습니다.

구조적 제한은 query별 MCP schema 최대 8개, retrieval input 80,000자, retrieval model turn/MCP call 각각 4회, no-progress 3회, tool result 6,000자, 선택 source 4개, augmentation 3,000 token입니다. 이 holdout은 회귀 검증용이며 공식 dashboard 점수를 대체하지 않습니다.

## 2026-08-22 Team A main + production_tool_v4 통합 회귀

`c617ea7`을 병합한 첫 v4 실행은 14/20(70%)이었습니다. `no_evidence` 뒤에 모델 파라미터 지식으로 소아 용량, 고혈압 목표 수치, 치료 단계 등을 추가한 실제 실패를 바탕으로 숫자 citation·새 정밀 수치·즉시 투약 중단·과도한 길이를 검사하고, 보정이 비거나 다시 위반하면 안전한 helpful fallback을 반환하도록 production과 evaluator를 일치시켰습니다.

| 검증 | 결과 |
|---|---:|
| 자동 테스트 | app 71/71 + eval 6/6 = 77/77 |
| 전체 v4 route holdout | 18/20 (90%), 완료 20/20, 오류 0 |
| Citation correctness / completeness | 100% / 100% |
| Unsupported addition / contradiction / deflection | 100% / 100% / 0% deflection rate |
| Groundedness / no-evidence / route | 95% / 95% / 95% |
| 총 token | 99,556 (input 77,949 / output 21,607) |
| 평균 latency / 응답 문자 | 17.034초 / 483.3자 |
| 남은 두 축 targeted 재검증 | 2/2 통과 |

마지막 두 실패는 특정 정답을 prompt에 추가하지 않고, 일반적인 간결 설명 표현을 direct signal로 확장하고 no-evidence 고지의 완결성을 검사하는 방식으로 수정했습니다. 이 결과는 공식 dashboard 점수가 아니며, 안전 보정으로 늘어난 호출 비용은 공식 token 사용량과 함께 관찰합니다.
