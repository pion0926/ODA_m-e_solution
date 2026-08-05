# 5-1 종료평가 결과보고서 27개 작성 파트

이 파일은 `backend/report_prompts.py`의 `EDITOR_REPORT_PARTS`를 사람이 검토하기 쉽게 요약한 문서다.

각 파트는 다음 정보를 가진다.

- `id`: AI 수정 요청 탭과 API 요청에 쓰는 파트 ID
- `sectionId`: 수정안을 저장할 에디터 섹션 ID
- `sampleHeadings`: 샘플 완성본 HWP에서 참고 발췌를 찾는 제목 키워드
- `requiredInputs`: 해당 파트를 완성하기 위해 필요한 자료
- `prompt`: 해당 파트만 작성하도록 제한하는 전용 프롬프트

현재 27개 파트:

1. `cover` - 표지
2. `toc` - 목차 및 작성 쪽수
3. `notice` - 평가보고서 관련 공지
4. `grade` - 평가등급 결과표
5. `summary-ko` - I. 평가결과 요약 1. 국문 요약
6. `project-background` - II. 대상사업개요 1. 사업 추진배경
7. `project-overview` - II. 대상사업개요 2. 사업개요
8. `pdm` - II. 대상사업개요 3. 사업설계매트릭스(PDM)
9. `eval-purpose` - III. 평가개요 1. 평가의 목적과 범위
10. `eval-matrix` - III. 평가개요 2. 평가매트릭스
11. `eval-methods` - III. 평가개요 3. 평가방법
12. `eval-limitations` - III. 평가개요 4. 평가의 한계
13. `eval-team` - III. 평가개요 5. 평가팀 구성 및 시행체계
14. `achievement` - IV. 성과 달성도
15. `criteria-relevance` - V. 기준별 평가결과 1. 적절성
16. `criteria-coherence` - V. 기준별 평가결과 2. 일관성
17. `criteria-effectiveness` - V. 기준별 평가결과 3. 효과성
18. `criteria-efficiency` - V. 기준별 평가결과 4. 효율성
19. `criteria-sustainability` - V. 기준별 평가결과 5. 지속가능성
20. `criteria-crosscutting` - V. 기준별 평가결과 6. 범분야 이슈
21. `criteria-other` - V. 기준별 평가결과 7. 그 외 평가기준
22. `conclusion` - VI. 결론 1. 결론
23. `working-factors` - VI. 결론 2. 작동요인
24. `nonworking-factors` - VI. 결론 2. 비작동요인
25. `theory` - VI. 결론 2. 변화이론 분석
26. `feedback` - VI. 결론 3. 환류과제
27. `lessons` - VI. 결론 3. 교훈

운영 원칙:

- AI 수정 요청은 선택된 `partId`의 프롬프트만 사용한다.
- 샘플 완성본은 해당 파트의 `sampleHeadings` 주변 텍스트만 참고문맥으로 넣는다.
- 샘플 문장을 복사하지 않고 구조, 근거 밀도, 문체만 참고한다.
- 자료가 부족한 항목도 빈칸으로 두지 않고 확인된 자료와 사업 맥락을 바탕으로 보수적으로 작성한다.
- 현재 HWP 자동 반영은 안전성 검증을 위해 `grade` 파트의 평가등급 결과표만 연결되어 있다.
