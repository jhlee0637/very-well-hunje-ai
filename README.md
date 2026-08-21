# Lunit Medical AI Hackathon — Team A Harness

Lunit의 hosted `Lunit/L2-preview` 모델과 MCP 검색 서버를 연결해 OpenAI 호환 API로 제공하는 Docker 실행 하네스입니다. Team A는 API·오케스트레이션·MCP·인용·Docker·통합 검증을 담당하고, Team B는 프롬프트·fixture·평가를 담당합니다.

## 실제 워크플로

```text
POST /v1/chat/completions
  → Generation L2 (retrieve_relevant_content만 노출)
  → 필요할 때 Python이 Retrieval L2 호출
  → Retrieval L2 (Lunit MCP 도구 + finalize_retrieval 노출)
  → 선택된 cite_uid 검증·중복 제거·크기 제한·숫자 인용 포매팅
  → 도구 결과를 Generation L2에 반환
  → 최종 답변
```

검색과 원문 청킹은 Lunit MCP가 담당합니다. MVP에는 DuckDB 재청킹이나 별도 벡터 DB를 넣지 않습니다. Python은 모델의 도구 호출을 실행하는 유한 상태 머신이며, evidence round, 호출 횟수, 중복 호출, 컨텍스트 크기와 전체 요청 시간을 제한합니다. Production 기본 evidence round는 live 검증에서 가장 안정적이었던 1이며, `LUNIT_RETRIEVAL_EVIDENCE_ROUND_LIMIT`으로만 실험적으로 늘릴 수 있습니다. 상세 계약은 [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)를 참고하세요.

## 주요 디렉터리

```text
app.py                         FastAPI 진입점
src/lunit_harness/api          OpenAI 호환 HTTP 계약
src/lunit_harness/clients      L2 및 MCP 클라이언트
src/lunit_harness/orchestration  Generation/Retrieval 상태 머신
src/lunit_harness/tools        MCP 실행·finalize·도구 결과 계약
src/lunit_harness/citations    근거 저장·검증·인용 포매팅
scripts                        preflight 및 안전한 smoke 도구
tests                          단위·통합·mock E2E 테스트
```

## 로컬 실행

Python 3.11 이상을 권장합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:LUNIT_FM_API_KEY = '<runtime secret>'
.\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
```

개발 머신에서는 Git에 포함되지 않는 `secrets.json`을 보조 입력으로 읽을 수 있습니다. Docker와 제출 환경에서는 반드시 `LUNIT_FM_API_KEY` 환경변수로 주입합니다. 키 값은 로그나 명령행 인자에 넣지 않습니다.

## 검증

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\preflight.py
.\.venv\Scripts\python.exe scripts\smoke_model.py
.\.venv\Scripts\python.exe scripts\smoke_mcp.py --call-data-sources
```

서버가 실행 중이면 전체 HTTP 경로를 확인합니다. 기본 질문은 MFDS 허가 근거가 확인된 타이레놀 적응증·금기 질의이므로 실제 모델/MCP/숫자 인용 경로를 검사합니다.

```powershell
.\.venv\Scripts\python.exe scripts\smoke_api.py
```

연결 없이 HTTP 계약만 확인하려면 `--skip-chat`을 사용합니다.

## Docker

```powershell
docker build -t lunit-team-a .
docker run --rm -p 8000:8000 -e LUNIT_FM_API_KEY lunit-team-a
```

TLS inspection을 사용하는 로컬 네트워크에서는 검증을 끄지 말고 공개 Root CA를
BuildKit secret으로 전달합니다. 이 옵션은 일반 제출 build에는 필요하지 않습니다.

```powershell
docker build --secret id=custom_ca,src=C:\path\to\local-root-ca.crt -t lunit-team-a .
```

이미지는 `app.py`, `src`, 선택된 production·retrieval prompt, 고정 버전 의존성만 복사합니다. `secrets.json`, `.env`, 개발 로그, 문서, 테스트는 이미지에서 제외합니다. 런타임에는 L2와 MCP의 HTTPS 엔드포인트에 접근할 수 있어야 합니다.

## Team B 프롬프트 연결

Team B가 품질 A/B에서 선택한 `production_tool_v4.md`와 `grounded_v1.md`를 통합했습니다. 비교와 롤백을 위해 v1·v2·v3도 보존하며, Docker image는 필요한 파일만 allowlist로 복사하고 아래 경로를 기본값으로 사용합니다.

```text
LUNIT_GENERATION_PROMPT_PATH=/app/prompts/generation/production_tool_v4.md
LUNIT_RETRIEVAL_PROMPT_PATH=/app/prompts/retrieval/grounded_v1.md
```

v4는 일반 의료·비의료 질문에는 직접 답하고, 근거가 실제로 필요한 복잡한 환자별 결정과 특정 guideline·법률·급여·허가·라벨·최신 문헌·정확한 수치·citation 질문에만 검색을 한 번 수행합니다. 환자·보호자·임상의를 대화에서 구분하고 사용자의 언어를 따르며, 명백한 일반·고수준 설명은 코드 게이트에서도 retrieval tool을 숨깁니다. Tool 결과 이후의 근거 제한, 숫자 인용, `partial`/`no_evidence`, prompt-injection 방어 계약은 유지합니다.

Generation 모델에는 `retrieve_relevant_content`만 보입니다. Retrieval 모델에는 MCP 도구와 로컬 `finalize_retrieval`만 보입니다. 정상 검색의 `no_evidence` 또는 빈 source는 확인하지 못한 범위를 밝힌 뒤 안전한 일반 조치·확인 단계·응급 경고를 제공하는 final Generation으로 이어지며, 정확한 수치나 citation을 만들지 않습니다. 근거가 있으면 모든 문장과 bullet 끝의 유효 숫자 인용을 검사하고 한 번만 교정합니다. 교정 후에도 불완전하면 검증된 인용 문장을 보존하고, 인용을 임의로 추가하지 않습니다. Credential, L2/MCP 연결, protocol 또는 deadline 문제는 임상적 `no_evidence`로 위장하지 않고 sanitized OpenAI-compatible 5xx 오류로 구분합니다. 잘못된 요청은 계속 4xx로 거부합니다.

Retrieval은 질의 의도에 맞는 MCP schema 최대 8개만 노출하며, model turn 4회·MCP call 4회·무진전 3회·누적 직렬화 입력 80,000자에서 중단합니다. Tool result는 6,000자, 선택 source는 4개, source당 800 token, augmentation은 3,000 token으로 제한합니다. Generation·retrieval·citation repair 출력 상한은 각각 2,048·512·768 token이고 repair에는 전체 대화를 재전송하지 않습니다. 최종 Generation 상한은 v4의 기존 27회 품질 평가 호출 중 15회가 1,024 token을 초과한 측정에 따라 복원했습니다.

## 2026-08-22 토큰 예산 hotfix 검증

- 독립 route holdout: 20/20, direct 10/10, retrieval 10/10, 모든 deterministic 평가 축 100%.
- Holdout 총 사용량: 35,390 tokens(input 28,240 / output 7,150), 평균 latency 4.905초.
- 최종 Docker direct smoke: 2,212 tokens, 12.11초, `finish_reason=stop`, retrieval·citation 없음.
- 실제 MFDS retrieval smoke: 8,234 tokens, 24.18초, 숫자 citation 존재. 이전 v2 smoke 19,977 tokens 대비 58.8% 감소했습니다.
- Team A main 통합 전 자동 테스트 66개 통과. Prompt/case와 결과 SHA는 `prompts/README.md`에 기록합니다.

이 결과는 로컬 L2/MCP smoke와 독립 fixture holdout이며 공식 dashboard 점수는 아닙니다. Trial 4의 4.05 및 17.5M tokens는 hotfix 전 비교 기준으로만 사용합니다.

## 2026-08-22 Team A main 통합 후 v4 검증

- Team A `c617ea7`의 bounded retrieval·conditional routing·compact finalization을 `Dev-hun`의 v4 prompt와 통합했습니다.
- 첫 v4 holdout은 14/20(70%)이었고, 실패 응답에서 no-evidence 이후 정확한 용량·목표 수치·치료 단계가 생성되는 문제를 확인했습니다.
- 안전 guard 적용 후 전체 20건이 오류 없이 완료되어 18/20(90%)을 통과했습니다. Citation correctness/completeness, unsupported addition, contradiction, deflection은 100%, groundedness·no-evidence·routing은 각각 95%였습니다.
- 남은 두 실패는 일반적인 "간단히 설명" 요청의 불필요한 retrieval과 불완전한 no-evidence 고지였습니다. 일반화된 routing/disclosure 조건으로 수정한 실제 L2 targeted 회귀는 2/2 통과했습니다.
- 20건 전체 실행은 99,556 tokens(input 77,949 / output 21,607), 평균 latency 17.034초였습니다. Guard 이전 76,254 tokens보다 증가한 부분은 no-evidence 보정 호출 비용이므로, 공식 결과에서 안전성 이득과 함께 계속 관찰합니다.

위 수치는 prompt에 문항 답을 포함하지 않은 원본 route holdout 및 fixture 기반 로컬 결과이며 공식 dashboard 점수가 아닙니다.

## 통합 회귀 결과

- Team B production prompt/case 해시는 handoff manifest와 일치합니다.
- 애플리케이션 자동 테스트 73개와 평가 루브릭 테스트 6개, 합계 79개가 통과했습니다. Preflight는 6 pass, 0 fail이며 현재 Codex Python 프로세스에서 credential 미주입과 Docker CLI 자동 탐지 실패를 warning으로 보고했습니다.
- 사용자 설치 Docker 29.7.2 Linux engine에서 image를 19.2초에 빌드했습니다. Direct smoke는 2,500 tokens와 604자 응답으로 종료됐고, 실제 MFDS retrieval smoke는 16,245 tokens와 숫자 citation을 반환했습니다.
- MFDS smoke에서 citation fallback이 15,735 tokens를 쓰고도 핵심 내용을 66자로 축소하는 회귀를 발견했습니다. Unknown citation label만 제거하고 내용은 보존하도록 바꾼 뒤 동일 질문이 397자로 회복됐으며 token 증가는 3.2%였습니다.
- Docker 실제 단일 턴과 지시어를 포함한 후속 턴은 HTTP 200, non-empty content, `finish_reason=stop`, 숫자 인용으로 통과했습니다.
- Team B raw prompt runner 재실행은 단일 턴 3/7, 다중 턴 0/3이었으며, 주요 실패 축은 sentence-level citation completeness였습니다. 이 raw runner는 production driver의 bounded repair와 deterministic filtering을 적용하지 않은 prompt-only 기준선입니다.

## 현재 제약

- `stream=true`는 OpenAI 형식의 400 오류로 명시적으로 거부합니다.
- 프롬프트 파일이 없으면 보수적인 내장 프롬프트를 사용합니다.
- 각 요청은 독립적인 예산과 근거 저장소를 사용하므로 대화 간 근거가 섞이지 않습니다.
- Docker Desktop Linux engine에서 build, 자동 startup, 이미지 secret 제외, 실제 L2/MCP 숫자 인용 E2E를 확인했습니다. 로컬 TLS inspection 환경에서는 위 BuildKit CA secret 옵션이 필요할 수 있습니다.
