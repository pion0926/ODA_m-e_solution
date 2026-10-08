# 19. 사업 기본정보가 PDM을 근거 문서로 표시함

## 원인

사업개요 생성과 latest_plan_overview 조회는 현재 활성 사업계획서만 사용하지만, renderProjectOverview는 별도로 조회한 pdm_source_document를 근거 링크로 표시했다. 안내문과 기존 화면 회귀 테스트도 이 잘못된 동작을 유지했다.

운영 knut 조회 결과 실제 overview.source_document_ids는 사업계획서 c6d5566b-dc65-46c8-843a-aecb5d0a5e56 하나였다. PDM d10c34e3-feda-4ba1-a3ab-ae15ca14d374는 실제 사업개요 생성 출처가 아니다.

## 수정

- API가 해당 사업개요의 실제 source_document_ids에서 project_plan 역할 문서를 확인하여 project_plan_source_document를 반환한다. PDM이나 일반자료로 대체하지 않는다.
- 기본정보 링크와 설명을 사업계획서 기준으로 수정한다. PDM 다운로드·성과지표 정보는 별도로 유지한다.
- 5개 언어에 새 번역 키를 사용하고 동적 근거 링크를 정적 번역이 덮어쓰지 않도록 한다. 웹 스크립트 버전을 변경한다.
- 생성 완료 계획서 부재/교체 시 기존 latest_plan_overview의 현재 계획서 일치 검증을 유지한다.

## 검증 및 배포

- 출처 API, 계획서/PDM 처리 분리, 화면 계약, 다국어 관련 테스트 55개 및 하위 테스트 2개 통과. JavaScript 구문 검사 통과.
- 개발 API·웹·워커 정상 기동 확인 후 V2.4.12 운영 배포. 운영 서비스 모두 healthy.
- 백업: .runtime/backups/production-20260929-161101
- 릴리스: .runtime/releases/V2.4.12-validated-20260929-161131
- knut 실제 운영 화면의 기본정보 링크가 c6d5566b-dc65-46c8-843a-aecb5d0a5e56 계획서를 가리키고, 별도 PDM 다운로드가 d10c34e3-feda-4ba1-a3ab-ae15ca14d374를 가리키는 것 확인.
- 화면: artifacts/knut-20260929/overview-plan-source.png
- 기존 평가/보고서 재생성 없음. evaluation_current=true, report_current=true, report_sections의 draft 27개 보존.
