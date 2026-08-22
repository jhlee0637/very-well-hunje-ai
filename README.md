# Lunit Medical AI Hackathon

Lunit L2 모델과 MCP 검색을 연결하는 OpenAI 호환 의료 RAG 서비스입니다. Python이 검색, 근거 선택, 인용 검증을 제한된 워크플로로 실행합니다.

## 동작

```text
conversation
  → Generation L2
  → Retrieval L2 (필요한 경우)
  → Lunit MCP
  → 근거 정리 및 인용 검증
  → assistant response
```

서비스는 `GET /v1/models`와 `POST /v1/chat/completions`를 제공합니다.

## 구조

```text
app.py                 API 진입점
src/lunit_harness/     실행 코드
prompts/               생성·검색 프롬프트
tests/                 단위·통합·E2E 테스트
eval/                  로컬 평가 케이스와 실행기
scripts/               사전 점검과 smoke test
docs/                  설계·대회·모델 문서
```

## 실행

```bash
python -m pip install -r requirements.txt
export LUNIT_FM_API_KEY="<runtime-key>"
uvicorn app:app --host 0.0.0.0 --port 8000
```

선택 설정은 `.env.example`을 참고합니다.

## 검증

```bash
pytest -q
python scripts/preflight.py
```

## Docker

```bash
docker build -t lunit-hackathon .
docker run --rm -p 8000:8000 -e LUNIT_FM_API_KEY="<runtime-key>" lunit-hackathon
```

세부 내용은 [문서 목록](docs/README.md)과 [아키텍처](docs/ARCHITECTURE.md)를 참고합니다.
