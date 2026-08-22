# Prompts

- generation/: 직접 답변, retrieval 요청, 근거 기반 최종 응답 지침
- retrieval/: MCP 검색과 evidence 선택 지침

Production 기본 프롬프트는 Dockerfile의 LUNIT_GENERATION_PROMPT_PATH와 LUNIT_RETRIEVAL_PROMPT_PATH에서 확인합니다.

평가 case, 실제 응답, 점수와 실행 결과는 Git에 저장하지 않습니다.
