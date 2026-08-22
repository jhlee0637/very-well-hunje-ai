1. 해커톤 규칙은 `./docs/HACKATHON.md`를 참고한다.
2. API key는 로컬 `secrets.json`에서만 참고한다. 값은 출력하거나 코드에 복사하지 않으며 Git과 Docker 이미지에 포함하지 않는다.
3. commit message는 변경 목적과 검증 결과가 드러나게 작성한다. 제목은 72자 이내를 권장한다.
4. 원격 변경을 가져올 때 최근 commit message와 diff를 먼저 확인한다.
5. L1 모델을 다룰 때는 `./docs/models/L1-16B-A3B.md`와 `./docs/models/L1-16B-A3B.json`을 먼저 읽는다.
6. 개인 브랜치는 서로 수정하지 않는다. Team A는 `Dev-jehee`, Team B는 `Dev-hun`을 사용한다.

# 프로젝트 구조

```text
.
├─ app.py
├─ Dockerfile
├─ requirements.txt
├─ src/lunit_harness/
│  ├─ api/
│  ├─ citations/
│  ├─ clients/
│  ├─ orchestration/
│  ├─ tools/
│  └─ validation/
├─ prompts/
│  ├─ generation/
│  └─ retrieval/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ e2e/
│  └─ fixtures/retrieval/
├─ eval/
│  ├─ cases/
│  └─ simulator_runner.py
├─ scripts/
└─ docs/
   ├─ ARCHITECTURE.md
   ├─ HACKATHON.md
   ├─ SUPPORT_PARAMETER.md
   ├─ CODEX_MCP_CONFIGURATION.md
   └─ models/
```

## Team A 담당

```text
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
```

## Team B 담당

```text
prompts/
tests/fixtures/retrieval/
eval/cases/
eval/simulator_runner.py
src/lunit_harness/validation/
```

## 브랜치 통합 규칙

- Team B 브랜치 root의 `Dockerfile`, `app.py`, `prompting.py`, `tests/test_app.py`는 실험 재현용으로 취급하고 production 제출물에 통합하지 않는다.
- production `Dockerfile`, root `app.py`, API와 orchestration 구현은 Team A가 소유한다.
- 개인 브랜치를 통째로 merge하지 않는다. 통합 전 diff를 검토하고 소유 경로만 선택적으로 반영한다.
- Team B 변경은 Team B 소유 경로만 통합한다.
- 소유 경로 밖의 변경이 필요하면 양 팀이 목적과 interface를 확인하고 사용자 승인 후 반영한다.
- `lunit/hackathon-submission`은 Docker build, 필수 API, L2/MCP orchestration, prompt/eval 계약을 검증한 뒤 사용자 승인에 따라 갱신한다.
