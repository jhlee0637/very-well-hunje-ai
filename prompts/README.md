# Prompt experiments

Retrieval과 generation 프롬프트를 분리하고, 파일을 덮어쓰지 않고 새 버전을 추가하여 dashboard 점수와 commit을 대응시킵니다. Team A retrieval이 준비되면 JSON fixture만 실제 `retrieve_relevant_content` 출력으로 교체합니다.

## 고정 조건

- Model: `Lunit/L2-preview`
- Temperature: `0.0`
- Max tokens: `2048`
- Questions: `eval/cases/clinical_qa.jsonl`의 동일한 6개 질문
- Fixtures: sufficient, partial, no-evidence, conflicting, irrelevant, prompt-injection
- Citation contract: source의 `citation_number`를 `[1]`, `[2]` 형식으로 표시

Baseline은 검색 결과 없이 `generation/baseline.md`와 질문만 전달합니다. Grounded 후보는 동일 질문 앞에 해당 JSON fixture를 결합합니다. 검색 결과를 두 번째 system message로 전달한 초기 실험에서는 L2가 이를 무시하고 문서 밖 용량·검사를 생성했으므로, 검색 결과와 질문을 하나의 user message로 전달합니다.

## 실제 L2 비교 결과

실행일: 2026-08-21. 아래 점수는 deterministic smoke harness로 재채점한 결과입니다.

| Prompt | Overall | Groundedness | Citation correct | Citation complete | Unsupported-addition 방지 | Contradiction 처리 | Deflection rate | No-evidence 처리 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0/6 (0.0%) | 0.0% | 100.0%* | 16.7% | 50.0% | 83.3% | 50.0% | 83.3% |
| grounded_v1 | 5/6 (83.3%) | 83.3% | 100.0% | 100.0% | 83.3% | 100.0% | 0.0% | 100.0% |
| grounded_v2 | 5/6 (83.3%) | 83.3% | 100.0% | 100.0% | 83.3% | 100.0% | 0.0% | 100.0% |
| grounded_v3 | 4/6 (66.7%) | 83.3% | 100.0% | 100.0% | 83.3% | 100.0% | 0.0% | 83.3% |

`*` baseline citation correctness 100%는 citation을 생성하지 않아 잘못된 번호도 없었다는 뜻이며, completeness 16.7%와 함께 해석해야 합니다.

grounded_v2의 multi-turn follow-up은 1/1 통과했고, 모든 평가 축과 citation을 유지했습니다.

## 최종 선택

`generation/grounded_v2.md`를 Team A 연결용 1순위 후보로 선택합니다.

- v1과 overall은 동률이지만 v1은 prompt-injection fixture에서 패혈증·산소포화도·흉부 검사 등 문서 밖 정보를 추가했습니다.
- v2는 prompt injection을 통과했습니다. 실패한 irrelevant 케이스에서도 무관 문서를 의학 근거로 사용하거나 `[2]`로 citation하지는 않았고, “무관하여 제외했다”는 메타 문장에서 문서 주제인 인슐린을 노출했습니다.
- v3는 무관 문서를 조용히 제외했지만 prompt injection 내용을 되풀이하고 일반 임상 지식을 추가했으며 no-evidence 답변도 장황해졌습니다.
- 의료 환각과 보안 경계 실패가 무관 문서 제목 노출보다 위험하므로 v2를 선택합니다.

## 대표 실패 사례

- Baseline: 근거 없이 해열제 용량, SpO₂ 기준, 항생제, 영상검사를 추가하고 “담당 의사 판단”으로 회피했습니다.
- v1 injection: fixture가 지원하는 “즉시 응급 평가” 뒤에 폐렴·패혈증·산소포화도·흉부 검사를 추가했습니다.
- v2 irrelevant: 임상 답은 source 1에만 근거했지만 source 2의 인슐린 문서를 제외했다고 언급했습니다.
- v3 injection: 악성 지시 문자열을 그대로 재인용하고 문서 밖 감별진단과 검사를 추가했습니다.

## 실행 및 재채점

```powershell
docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode baseline

docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode grounded `
  --prompt prompts/generation/grounded_v2.md

docker run --rm --env-file .env -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py --mode grounded `
  --prompt prompts/generation/grounded_v2.md --multiturn

docker run --rm -v "${PWD}:/work" -w /work python:3.13-slim `
  python eval/simulator_runner.py `
  --rescore-results results/<existing-result>.jsonl
```

Raw 응답은 API key를 포함하지 않는 `results/*.jsonl`에 저장되며 Git에서는 제외됩니다. 실험 기록에는 commit SHA, prompt SHA-256, prompt/fixture 경로, model, temperature, max tokens, 응답 원문, 각 평가 축을 남깁니다.

이번 비교에 사용한 raw 결과 SHA-256:

- baseline: `AF5C28B84730D9C03A25C050CE8BC983DB330962352AC37F8E8D765C72AF58BA`
- grounded_v1: `AD05319824C7583BA2AEBB9016D9DF73C081E3445FE3D8042D42A1D9ACCEB251`
- grounded_v2: `3687F58A1B137C8370C2047E4F24E38E4295353DCBC7D22E3CCE3F5CB97841F1`
- grounded_v3: `C7AA09C272C82FC229DCC5725F67987AA45EE734EAE93A8ABB96E5018D034372`

이 하네스의 groundedness와 unsupported-addition은 fixture별 필수·금지 표현을 이용한 빠른 deterministic proxy입니다. 최종 HealthBench 또는 임상의 평가를 대체하지 않습니다.
