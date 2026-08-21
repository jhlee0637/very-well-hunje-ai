# very-well-hunje-ai

루닛 의과학 특화 파운데이션 모델 해커톤 프로젝트입니다.

## L2 pure baseline

검색, MCP tool, RAG 없이 `Lunit/L2-preview` 모델만 호출하여 baseline을 측정합니다.

### 1. 환경변수 설정

PowerShell:

```powershell
$env:LUNIT_FM_API_URL = "https://model.hackathon.lunit.io"
$env:LUNIT_FM_API_KEY = "lunit_..."
$env:LUNIT_FM_MODEL = "Lunit/L2-preview"
```

API key는 파일이나 Git에 저장하지 마세요.
또는 `.env.example`을 `.env`로 복사한 뒤 로컬 `.env`에 키를 설정할 수 있습니다. `.env`는 Git에서 제외됩니다.

### 2. Smoke test

```powershell
python scripts/run_baseline.py --limit 1
```

### 3. 전체 기본 질문 실행

```powershell
python scripts/run_baseline.py
```

결과는 `results/baseline_<timestamp>.jsonl`, 요약은 같은 이름의 `.summary.json`에 저장됩니다. `results/`는 Git에 추적되지 않습니다.

### 사용자 질문 세트

UTF-8 JSONL 형식을 사용합니다. 각 줄에 `id`, `prompt`, 선택적 `reference` 필드를 넣을 수 있습니다.

```powershell
python scripts/run_baseline.py --input data/my_questions.jsonl
```

baseline은 응답 성공률, latency, token usage를 집계합니다. 실제 HealthBench 점수는 생성된 제출물을 Lunit dashboard에 제출해 확인해야 합니다.

## Mock Context grounding test

현재 드라이버와 로컬 하네스는 `prompting.py`의 `MOCK_CONTEXT`를 근거 문서로 주입합니다. 생성 프롬프트는 임상의를 대상으로 직접 답변하고, 의뢰 전 구체적인 1차 관리 지침을 제시하며, 문서 밖 내용을 추가하지 않고 모든 의학적 주장에 `[출처: 문서ID]`를 붙이도록 요구합니다.

내장 Mock 문서로 한 문항을 확인하려면:

```powershell
py scripts/run_baseline.py --limit 1
```

코드를 수정하지 않고 다른 Mock 문서를 실험하려면 문서 본문에 `[문서ID: ID]`를 포함한 UTF-8 텍스트 파일을 넘깁니다.

```powershell
py scripts/run_baseline.py --limit 1 --context-file data/my_mock_context.txt
```

결과 JSONL에는 각 응답에 실제 사용한 `context`가 함께 기록되어 실험을 재현할 수 있습니다. 실제 retrieval이 연결되면 `prompting.build_grounded_messages`의 `context` 인자에 검색 결과를 전달하면 됩니다.

## Hackathon submission driver

저장소 루트의 `Dockerfile`은 pure L2 baseline을 OpenAI-compatible service로 실행합니다.

```powershell
docker build -t very-well-hunje-ai:local .
docker run --rm -p 8000:8000 --env-file .env very-well-hunje-ai:local
```

제공 endpoint:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `GET /health`

주최 측 evaluation은 `lunit/hackathon-submission` branch의 HEAD SHA를 사용합니다.
