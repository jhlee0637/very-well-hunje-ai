1. 대회 규칙 원문은 로컬 doc/HACKATHON.md에서만 참고하고 Git에 포함하지 않는다.
2. API key와 runtime credential은 출력하거나 코드에 복사하지 않으며 Git과 Docker 이미지에 포함하지 않는다.
3. 실제 MCP 응답, 평가 case, 실행 결과와 작업 로그는 로컬 전용으로 관리한다.
4. commit message는 변경 목적과 검증 결과가 드러나게 작성한다.
5. 개인 브랜치는 서로 수정하지 않는다. Team A는 Dev-jehee, Team B는 Dev-hun을 사용한다.

# 공개 저장소 구조

~~~text
.
├─ app.py
├─ Dockerfile
├─ requirements.txt
├─ src/lunit_harness/
├─ prompts/
├─ scripts/
└─ doc/
~~~

## 소유 경계

- Team A: API, orchestration, MCP/model client, citation, Docker와 실행 스크립트
- Team B: generation/retrieval prompt와 response validation
- 로컬 전용: doc/HACKATHON.md, eval/, tests/, 결과 파일과 작업 로그

개인 브랜치를 통째로 merge하지 않는다. 소유 경로의 diff를 검토한 뒤 선택적으로 통합한다.
lunit/hackathon-submission은 사용자 승인과 secret 검사를 거쳐 갱신한다.
