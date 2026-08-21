# Prompt experiments

프롬프트는 retrieval과 generation 단계로 분리합니다. 파일을 수정해 덮어쓰기보다 새 버전을 추가하여 dashboard 점수와 정확히 대응시킵니다.

## 권장 비교 순서

1. `generation/baseline.md`로 비검색 기준점을 측정합니다.
2. `generation/grounded_v1.md`와 `tests/fixtures/retrieval/sufficient.json`으로 기본 흡수율을 확인합니다.
3. `generation/grounded_v2.md`를 다섯 retrieval fixture에 모두 적용합니다.
4. unsupported addition, citation 누락, deflection, conflict 은폐, prompt injection 준수 여부를 기록합니다.
5. 실제 retrieval 연결 시 `retrieval/grounded_v1.md`를 사용하고 generation 점수와 retrieval 실패를 분리해 분석합니다.

프롬프트 실험 기록에는 최소한 commit SHA, 프롬프트 경로, fixture 경로, 모델, temperature, 응답 원문을 남깁니다.
