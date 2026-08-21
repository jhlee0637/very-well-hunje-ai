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

검색과 원문 청킹은 Lunit MCP가 담당합니다. MVP에는 DuckDB 재청킹이나 별도 벡터 DB를 넣지 않습니다. Python은 모델의 도구 호출을 실행하는 유한 상태 머신이며, 호출 횟수·중복 호출·컨텍스트 크기·전체 요청 시간을 제한합니다. 상세 계약은 [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)를 참고하세요.

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

Team B가 선택한 `production_tool_v1.md`와 `grounded_v1.md`를 LF 기준 재현 해시로 통합했습니다. Docker image는 두 파일을 allowlist로 복사하고 아래 경로를 기본값으로 사용합니다.

```text
LUNIT_GENERATION_PROMPT_PATH=/app/prompts/generation/production_tool_v1.md
LUNIT_RETRIEVAL_PROMPT_PATH=/app/prompts/retrieval/grounded_v1.md
```

Generation 모델에는 `retrieve_relevant_content`만 보입니다. Retrieval 모델에는 MCP 도구와 로컬 `finalize_retrieval`만 보입니다. `no_evidence` 또는 빈 source는 모델을 다시 호출하지 않고 `제공된 문서에서 확인할 수 없음`으로 종료하며, 근거가 있으면 모든 문장과 bullet 끝의 유효 숫자 인용을 검사하고 한 번만 교정합니다. 교정 후에도 누락된 문장은 삭제하고 유효 인용 문장만 보존하며, 인용을 임의로 추가하지 않습니다. 유효한 evaluator 요청 중 runtime credential, L2/MCP 연결 또는 deadline 문제가 발생하면 같은 고정 문구를 OpenAI-compatible HTTP 200 completion으로 반환하고 `X-Lunit-Degraded: true`를 표시합니다. 잘못된 요청은 계속 4xx로 거부합니다.

## 통합 회귀 결과

- Team B production prompt/case 해시는 handoff manifest와 일치합니다.
- Production driver 자동 테스트 44개와 preflight 8개 항목이 모두 통과했습니다.
- Docker 실제 단일 턴과 지시어를 포함한 후속 턴은 HTTP 200, non-empty content, `finish_reason=stop`, 숫자 인용으로 통과했습니다.
- Team B raw prompt runner 재실행은 단일 턴 3/7, 다중 턴 0/3이었으며, 주요 실패 축은 sentence-level citation completeness였습니다. 이 raw runner는 production driver의 bounded repair와 deterministic filtering을 적용하지 않은 prompt-only 기준선입니다.

## 현재 제약

- `stream=true`는 OpenAI 형식의 400 오류로 명시적으로 거부합니다.
- 프롬프트 파일이 없으면 보수적인 내장 프롬프트를 사용합니다.
- 각 요청은 독립적인 예산과 근거 저장소를 사용하므로 대화 간 근거가 섞이지 않습니다.
- Docker Desktop Linux engine에서 build, 자동 startup, 이미지 secret 제외, 실제 L2/MCP 숫자 인용 E2E를 확인했습니다. 로컬 TLS inspection 환경에서는 위 BuildKit CA secret 옵션이 필요할 수 있습니다.
