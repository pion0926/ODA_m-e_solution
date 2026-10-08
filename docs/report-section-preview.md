# 선택 섹션 AI 수정·rHWP 미리보기

2026-09-12 후속 요청 반영: 직접 본문 편집/수동 저장 UI를 제거하였다. 아래 사용 절차가 최신이며, 최초 구현 QA 기록의 직접 편집 시험은 당시 버전에 대한 이력이다.

## 사용자 동작

1. 보고서 자동작성에서 왼쪽의 섹션을 선택한다.
2. 가운데 AI 수정 요청 패널과 오른쪽의 실제 rHWP 조판 화면을 함께 본다. 본문 직접 편집 칸은 없다.
3. `수정 요청 반영`은 서버에 저장된 현재 섹션 본문과 입력한 수정 지시를 전송한다. 완료 상태를 조회하여 저장된 새 본문을 불러오고 미리보기를 갱신한다.
4. 새 자료 업로드 후 재평가가 필요한 경우 버튼 아래 차단 사유 및 `DAC 재평가로 이동`을 표시한다. 재평가를 자동 실행하거나 안전 조건을 우회하지 않는다.
5. 왼쪽 27개 섹션 목차는 항상 표시한다. 접기/펼치기 기능은 제거하였다. 일반 초안 배지는 표시하지 않고 생성 중·오류·빈 섹션만 구분한다.
6. `미리보기 크게`는 AI 패널을 일시적으로 숨긴다. `AI 수정 요청 같이 보기`로 돌아온다.
7. 최종 다운로드 파일은 기존 `HWPX 저장`으로 생성한다. 미리보기만으로 기존 다운로드 파일을 덮어쓰지 않는다.

작업 화면은 다른 메뉴와 동일하게 본문 영역 좌우에 각각 200px 여백을 두고 나머지 폭을 사용한다. 목차는 항상 표시하며, 한글 미리보기는 최대 A4 폭(210mm, CSS 기준 약 794px)으로 제한하고 나머지 폭은 AI 패널이 사용한다. 좁은 화면에서는 미리보기도 화면에 맞춰 축소한다. AI 입력창은 16px/최소 200px로 표시한다. 한글 미리보기의 `−`, `+`, `100%`, `폭 맞춤`은 실제 rHWP 배율을 조절한다. 화면 폭이 바뀌면 미리보기도 다시 폭에 맞춘다. 문서 자체 여백이나 글꼴 크기를 변경하는 기능은 아니다.

## 편집 범위

- rHWP 화면 자체는 **읽기 전용 양식 검토 화면**이다. 캔버스에서 직접 문장/표를 수정하는 양방향 HWPX 편집은 제공하지 않는다.
- 본문 원본은 기존 `report_sections.content`이다. 화면에서 본문을 직접 수정하지 않고 AI 요청으로 변경한다. 글꼴, 표, 들여쓰기, 문단 규칙은 기존 독립 HWPX 어댑터에서 적용한다.
- 프리뷰는 선택한 논리 섹션만 포함한 임시 HWPX이다. 선택 섹션이 길면 여러 쪽이 표시된다.
- 화면의 쪽수는 섹션 내부 쪽수다. 최종 전체 보고서의 실제 쪽수와 목차는 기존 전체 저장·조판 단계에서 확정한다.
- 변화이론 그림은 최근 같은 프로젝트의 저장본을 사용한다. 본문은 즉시 미리보기 가능하지만 그림 재생성은 전체 HWPX 저장 단계에 남겨두었다. 최근 그림이 없으면 무관한 원본 예시 그림을 표시하지 않는다.
- 섹션별 수정 요청 문구는 현재 열린 화면 메모리에 유지한다. 브라우저 새로고침/종료 후 복원을 보장하지 않는다.

## 처리 흐름과 코드 경계

`AI 수정 요청 → 기존 섹션 원본 저장 → 운영 HWPX 어댑터 → 선택 섹션 분리 → 임시 HWPX → rHWP loadFile`

| 책임 | 파일 |
|---|---|
| 서비스 화면 배치 | `0821_OoooDaon_v1.0.html` |
| 편집/저장/AI 완료 연동 | `assets/odaon-v1-live.js` |
| 미저장 초안/진행 상태 | `assets/report-section-flow.js` |
| 디바운스, 최신 응답 판별, rHWP 통신 | `assets/report-section-preview.js` |
| 편집·미리보기 레이아웃 | `assets/report-section-preview.css` |
| rHWP 읽기 전용 모드 | `assets/rhwp/section-preview-mode.js` |
| 미리보기 HTTP API | `redesign/backend/kodame_intake/report_preview_api.py` |
| 임시 HWPX 생성/분리/패키징 | `redesign/backend/kodame_intake/report_section_preview.py` |
| 27개 논리 섹션 시작·끝 경계 | `config/report_section_preview.json` |
| 원본 및 임시 편집 내용의 공통 준비 | `report_exporter.py::_pipeline_context(content_overrides=None)` |
| 공통 운영 어댑터 | `redesign/backend/kodame_intake/hwpx_adapters/sections/section*.py` |
| 공통 문단·표 레이아웃 | `redesign/backend/kodame_intake/hwpx_layout/` |

기존 전체 보고서는 27개 논리 섹션을 여러 물리 HWPX 구역에 담는다. 미리보기는 해당 물리 구역에 동일한 어댑터와 레이아웃 처리를 적용한 후 제목 경계로 선택 섹션만 분리한다. 표 안의 제목처럼 보이는 문자열은 경계로 사용하지 않는다. 고정 양식 변경 시 경계 JSON과 테스트를 함께 수정해야 한다.

임시 문서는 `section0.xml` 하나, `secCnt=1`, manifest/spine 참조 하나로 패키징한다. 다른 구역을 복구하는 전체 보고서용 ZIP repacker는 임시 문서에 적용하지 않는다. 목차는 동일한 고정 열 우측 정렬 함수를 구역 경로만 바꾸어 재사용한다.

## 안정성·보안

- 미리보기 API는 기존 로그인, 메뉴 권한, 프로젝트 RLS를 따른다. 파일 경로와 프로젝트 ID를 클라이언트 입력으로 받지 않는다.
- 미리보기에는 LLM 호출, 원본 저장, export job 생성이 없다. 응답은 `Cache-Control: no-store`이다.
- 입력/선택별 버전 번호를 비교하여 늦게 도착한 이전 내용을 표시하지 않는다. 동시에 여러 rHWP `loadFile`을 실행하지 않는다.
- 조판 중에는 이전 섹션의 페이지를 숨긴다. 실패해도 원본 편집은 유지하고 재시도할 수 있다.
- iframe 초기 로딩과 RPC 대기는 제한 시간을 둔다. 실패 후 새로고침은 iframe도 다시 불러온다.
- 미리보기 갱신이 편집 창의 입력 포커스와 커서를 빼앗지 않도록 복원한다.
- AI 요청은 선택 섹션에만 POST한다. 수동 편집용 PUT API의 버전 충돌 검사는 기존 호환성을 위해 유지하지만 현재 화면에서는 호출하지 않는다.
- `ReportSectionFlow.generationBlock`에서 버튼 비활성화 사유를 하나의 규칙으로 관리한다. 요청 직전 lifecycle을 다시 확인하고, 12초 주기/화면 재진입/상태 재확인에서 최신 상태를 반영한다.
- 저장/상태 목록 조회 중 사용자가 다른 섹션을 선택하면 이전 섹션으로 되돌리지 않는다.
- 부모↔iframe 메시지는 같은 origin과 정확한 window를 확인한다. proof 모드의 허용 RPC는 읽기/로드 명령으로 제한한다.

## 검증 위치

- 백엔드 회귀: `redesign/backend/tests/test_report_section_preview.py`
- 프런트엔드 상태/미리보기: `redesign/frontend/test_report_section_flow.cjs`, `test_report_section_preview.cjs`
- KNUT 27개 실데이터 read-only 생성: `scripts/qa_section_preview.py`
- 인증/미리보기/충돌 저장 HTTP 시험: `scripts/qa_section_preview_api.py`
- 이번 검증 기록: `docs/qa/reports/FT-20260912-section-rhwp-edit-preview.md`
- AI 요청 전용 UI 후속 검증: `docs/qa/reports/FT-20260912-ai-request-only-ui.md`, `redesign/frontend/test_report_ai_request_ui.cjs`
