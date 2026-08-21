1. 해커톤 규칙은 ./doc/HACKATHON.md 를 참고할 것
2. API key는 ./secrets.json 파일을 참고하되 밸류값 자체는 출력하거나 코드에 복사하지 말 것. 그리고 .gitignore에 들어가있는지 확인하고 git으로 올라가지 않도록 할 것.
3. commit message는 항상 상세하게 할 것. 제목은 72자 이내를 권장하되, 본문 길이는 제한하지 않는다.
4. git clone/pull 등 github의 내용을 불러올 때는 commit message를 읽어서 이전 작업을 먼저 이해한 다음 작업할 것.
5. L1 모델의 구조나 특성을 다루는 작업에서는 ./doc/models/L1-16B-A3B.md 와 ./doc/models/L1-16B-A3B.json 을 먼저 읽을 것.
6. 팀원A와 팀원B의 개인 브랜치는 서로 관여하지 않습니다. 팀원A의 브랜치 Dev-jehee. 팀원B의 브랜치 Dev-hun.

# 프로젝트 폴더구조 방향
'''
main/
├─ Dockerfile
├─ .dockerignore
├─ .gitignore
├─ requirements.txt
├─ app.py
├─ AGENTS.md
├─ CODEX_HISTORY_JEHEE.log
├─ secrets.json                    # 로컬 전용, 이미지/Git 제외
│
├─ src/
│  └─ lunit_harness/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ errors.py
│     │
│     ├─ api/
│     │  ├─ __init__.py
│     │  ├─ routes.py
│     │  └─ schemas.py
│     │
│     ├─ orchestration/
│     │  ├─ driver.py
│     │  ├─ conversation.py
│     │  ├─ generation_phase.py
│     │  ├─ retrieval_phase.py
│     │  └─ budgets.py
│     │
│     ├─ clients/
│     │  ├─ model_client.py
│     │  └─ mcp_client.py
│     │
│     ├─ tools/
│     │  ├─ registry.py
│     │  ├─ executor.py
│     │  ├─ finalize_retrieval.py
│     │  ├─ retrieve_relevant_content.py
│     │  └─ result_formatter.py
│     │
│     ├─ citations/
│     │  ├─ models.py
│     │  ├─ store.py
│     │  └─ formatter.py
│     │
│     └─ validation/
│        ├─ tool_calls.py
│        └─ responses.py
│
├─ prompts/
│  ├─ retrieval/
│  │  ├─ baseline.md
│  │  └─ grounded_v1.md
│  ├─ generation/
│  │  ├─ baseline.md
│  │  ├─ grounded_v1.md
│  │  └─ grounded_v2.md
│  └─ README.md
│
├─ tests/
│  ├─ unit/
│  │  ├─ test_conversation.py
│  │  ├─ test_tool_executor.py
│  │  ├─ test_finalize_retrieval.py
│  │  └─ test_citation_formatter.py
│  ├─ integration/
│  │  ├─ test_retrieval_phase.py
│  │  ├─ test_generation_phase.py
│  │  └─ test_chat_completions.py
│  ├─ e2e/
│  │  └─ test_multiturn_driver.py
│  └─ fixtures/
│     ├─ model/
│     ├─ mcp/
│     └─ retrieval/
│        ├─ sufficient.json
│        ├─ partial.json
│        ├─ no_evidence.json
│        ├─ conflicting.json
│        └─ prompt_injection.json
│
├─ eval/
│  ├─ simulator_runner.py
│  ├─ cases/
│  │  ├─ clinical_qa.jsonl
│  │  └─ multiturn_qa.jsonl
│  └─ reports/                     # Git 제외
│
├─ scripts/
│  ├─ smoke_api.py
│  ├─ smoke_model.py
│  ├─ smoke_mcp.py
│  └─ preflight.py
│
└─ doc/
   ├─ HACKATHON.md
   ├─ SUPPORT_PARAMETER.md
   ├─ CODEX_MCP_CONFIGURATION.md
   ├─ ARCHITECTURE.md
   └─ models/
      ├─ L1-16B-A3B.md
      └─ L1-16B-A3B.json
'''

## 팀원 A의 담당 영역
'''
app.py
Dockerfile
requirements.txt
src/lunit_harness/api/
src/lunit_harness/orchestration/
src/lunit_harness/clients/
src/lunit_harness/tools/
src/lunit_harness/citations/
scripts/
tests/integration/
tests/e2e/
'''

## 팀원 B의 담당 영역
'''
prompts/
tests/fixtures/retrieval/
eval/cases/
eval/simulator_runner.py
src/lunit_harness/validation/
'''

