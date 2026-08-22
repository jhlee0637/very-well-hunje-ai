# Lunit Medical AI Hackathon

Lunit L2 모델과 MCP 검색을 연결하는 OpenAI 호환 의료 RAG 서비스입니다.

## 구조

~~~text
app.py                 API 진입점
src/lunit_harness/     실행 코드
prompts/               생성·검색 프롬프트
scripts/               사전 점검과 smoke test
doc/                  설계와 모델 문서
~~~

## 실행

~~~bash
python -m pip install -r requirements.txt
export LUNIT_FM_API_KEY="<runtime-key>"
uvicorn app:app --host 0.0.0.0 --port 8000
~~~

## 검증

~~~bash
python scripts/preflight.py
~~~

## Docker

~~~bash
docker build -t lunit-hackathon .
docker run --rm -p 8000:8000 -e LUNIT_FM_API_KEY="<runtime-key>" lunit-hackathon
~~~

대회 규칙 원문, API key, 평가 자료와 실행 결과는 저장소에 포함하지 않습니다.

세부 구조는 [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)를 참고합니다.
