# K-ODAME QA

| 요청 유형 | 실행 문서 | 범위 |
|---|---|---|
| 화면 QA / UI 확인 | [UI 회귀 테스트셋](ui-regression-testset.md) | 로그인 후 전체 화면, 프로젝트별 제공 언어, 글자·레이아웃·오류·새로고침 |
| 풀테스트 / 전체 흐름 테스트 | [풀테스트 계획](full-test-plan.md) | 관리자 다국어 프로젝트 생성·수행자 배정부터 71개 업로드, 분석, 지표, DAC, 보고서, HWPX |
| 사용자 우려사항 재검증 / 최종 릴리스 게이트 | [사용자 우려사항 통합 회귀 QA TC](user-concern-regression-testset.md) | 로그인·권한·자동배정·대시보드·성과관리·종료평가·27×2 생성/적용·few-shot·HWPX/rHWP 강화 회귀 |
| 보고서 27개 섹션 평가 | [27개 섹션별 QA 체크리스트](report-27-section-qa-checklist.md) | 섹션별 내용·근거·구조·양식 평가 후 HWPX 저장 및 rhwp 최종 미리보기 |
| 샘플 기반 보고서 구성 기준 | [종료평가 보고서 구성 기준](sample-report-composition-standard.md) | 완성 PDF 5건 기반 목차·계층·줄바꿈·표·사람이 읽는 출처와 업로드 파일명 노출 금지 |

- [풀테스트 입력자료 기준](full-test-corpus.md)
- [풀테스트 결과 템플릿](full-test-result-template.md)
- 실행별 결과는 `reports/`에 저장한다.
- 화면 증적은 `screenshots/`, 풀테스트별 산출물은 실행별 하위 폴더에 저장한다.
