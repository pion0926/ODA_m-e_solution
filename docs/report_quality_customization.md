# 종료평가 보고서 품질 설정·수정 가이드

이 문서는 보고서 내용 생성, HWPX 조판, 최종 검증을 한 파일에 섞지 않고 기능별로 수정하기 위한 안내서다. 보고서 품질 수치는 `config/report_quality_profile.json`, 섹션별 작성 지시는 `prompts/Section*.py`, 공통 문체 제한은 `backend/report_writing_policy.py`에서 변경한다.

## 1. 처리 흐름

1. 27개 섹션 프롬프트가 각각 초안을 생성한다.
2. `editor_prompt_runner.py`가 모든 섹션에 공통 few-shot 정책과 금지 규칙을 결합한다.
3. `report_writing_policy.py`가 반복 라벨, 상투 문구, 작성자 메모를 차단한다.
4. HWPX 어댑터가 초안의 의미 단위를 원본 양식 슬롯으로 옮긴다.
5. `hwpx_layout`의 기능별 모듈이 표 분할, 여백, 쪽 나눔, 목차, 쪽 번호를 적용한다.
6. Kordoc 1차 조판으로 목차 쪽수를 계산하고, 안정화 후 동일 값을 다시 적용한다.
7. 로컬 패키지·의미·조판·이미지 바이트 검증과 Kordoc 2차 검증을 통과한 파일만 저장한다.
8. 최종 제출 전 rHWP에서 실제 화면을 확인한다.

## 2. 사용자가 직접 수정할 파일

| 목적 | 파일 | 수정 단위 |
|---|---|---|
| 표 페이지 수, 행 그룹, 글자 크기, 셀 여백 | `config/report_quality_profile.json` | `layout.grade_table`, `pdm_table`, `achievement_table`, `recommendation_tables` |
| 쪽 번호·꼬리말 식별자 | `config/report_quality_profile.json` | `layout.page_identity` |
| 목차 rHWP 보정값 | `config/report_quality_profile.json` | `toc.project_overrides` |
| 시각자료 제목·색상·크기 | `config/report_quality_profile.json` | `layout.supplemental_visuals` |
| 섹션별 생성 지시와 few-shot 예시 | `prompts/Section1_*.py` ~ `prompts/Section27_*.py` | 섹션별 `SYSTEM_PROMPT`, `USER_PROMPT` |
| 모든 섹션 공통 문체·금지어 | `backend/report_writing_policy.py` | 공통 작성 정책과 품질 차단 규칙 |
| 소제목 요약어 선택 | `backend/report_outline.py` | 섹션·내용별 라벨 사전 |
| few-shot 공통 결합 | `prompts/editor_prompt_runner.py` | 공통 예시 주입 및 프롬프트 조립 |

샘플 보고서는 형식·논리 순서·문장 역할만 참고한다. 국가명, 사업명, 수치, 판단, 고유명사와 결론은 현재 프로젝트의 등록 근거에서만 생성하도록 공통 정책이 적용된다.

## 3. HWPX 기능 모듈

| 기능 | 코드 |
|---|---|
| 평가등급 결과표 2쪽 분할·1pt 셀 여백·산정 이유 | `redesign/backend/kodame_intake/hwpx_layout/grade_table.py` |
| PDM 3분할·열 너비·영문 줄바꿈 | `redesign/backend/kodame_intake/hwpx_layout/tables.py` |
| 평가매트릭스 분할·반복 머리행 | `redesign/backend/kodame_intake/hwpx_layout/tables.py` |
| 성과달성도 4쪽 분할·전체 텍스트 보존 | `redesign/backend/kodame_intake/hwpx_layout/tables.py` |
| 사업개요 상단 시작·작성 메모 제거 | `redesign/backend/kodame_intake/hwpx_layout/project_overview.py` |
| 환류과제·교훈 분할 | `redesign/backend/kodame_intake/hwpx_layout/recommendations.py` |
| 변화이론·등급·성과 도식 프레임 | `redesign/backend/kodame_intake/hwpx_layout/theory.py` |
| DAC 등급·성과/후속조치 이미지 생성 | `redesign/backend/kodame_intake/report_visuals.py` |
| 실제 목차 값 적용·검증 | `redesign/backend/kodame_intake/hwpx_layout/toc.py` |
| 꼬리말 식별자·하단 중앙 쪽 번호 | `redesign/backend/kodame_intake/hwpx_layout/page_identity.py` |
| 전체 단계 조립·2회 조판·최종 저장 | `redesign/backend/kodame_intake/report_exporter.py` |
| 원본 ZIP 엔트리와 생성 이미지 보존 | `backend/oda_me/hwpx/patchers.py` |

## 4. 주요 설정 예

### 평가등급표 페이지 구성

`layout.grade_table.page_row_groups`의 각 배열이 한 페이지다. `0`은 반복 머리행이며, 현재는 1쪽 `0~10`, 2쪽 `0, 11~19`로 구성된다. 셀 상하 여백은 `cell_margin_vertical: 100`, 즉 1pt다.

### 성과달성도 페이지 구성

`layout.achievement_table.page_item_groups`에서 14개 지표를 `4/4/3/3`개로 나눈다. `preserve_full_cell_text`는 항상 `true`로 두어야 생략부호가 생기지 않는다.

### 꼬리말과 쪽 번호

`layout.page_identity.header_text`는 내부적으로 기존 머리말 프레임을 꼬리말로 재사용하는 문서 식별 문자열이다. rHWP가 반복 머리말과 첫 본문 줄을 같은 기준선에 그리는 문제 때문에 식별자는 하단 좌측, 쪽 번호는 `BOTTOM_CENTER`에 배치한다.

### 프로젝트별 목차 보정

Kordoc과 rHWP의 페이지 계산이 다를 수 있다. 최종 rHWP에서 확인한 시작 쪽은 `toc.project_overrides`의 프로젝트 제목 포함 조건 아래에 기록한다. 키를 추가할 때는 `REQUIRED_TOC_KEYS`에 존재하는 키만 사용해야 하며, 내보내기 단계에서 모든 표시값을 다시 검증한다.

## 5. 프롬프트 수정 원칙

- 각 섹션 프롬프트는 좋은 예와 나쁜 예를 포함한 few-shot 구성으로 유지한다.
- 예시는 형식만 모방하고 예시의 사업 내용·수치·판단을 가져오지 않도록 명시한다.
- 결과는 HWPX 어댑터가 요구하는 구조를 그대로 출력해야 한다. 표 섹션의 열 이름과 JSON 키를 임의로 바꾸지 않는다.
- `~~음`, `~~함`, `~~임` 중심의 개조식 문체와 `ㅇ`/`-` 계층 규칙을 지킨다.
- `(근거 기반 판단)`, `(후속 과제)`, `관련 근거가 확인됨` 같은 범용 문구를 반복하지 않는다.
- 독자용 본문에는 업로드 파일명과 `(문서명, p. n)` 인용을 출력하지 않는다.

## 6. 검증 명령과 수용 기준

전체 회귀 테스트:

```powershell
docker compose run --rm -T -v "C:\Users\aimne\Project\ODAME\redesign\backend\tests:/app/redesign/backend/tests:ro" kodame-redesign-api python -m unittest discover -s /app/redesign/backend/tests
```

최종 내보내기는 다음을 모두 통과해야 한다.

- ZIP·필수 XML·27개 의미 섹션 완전성
- 평가등급 2쪽, PDM 3쪽, 성과달성도 4쪽, 환류·교훈 읽기 안전 분할
- 목차 모든 라벨과 표시 쪽수 일치
- 3개 시각자료가 현재 생성 바이트와 정확히 일치
- 금지 문구·작성 메모·업로드 파일명·마크다운·생략부호 없음
- rHWP에서 목차, 핵심 표, 시각자료, 마지막 페이지 직접 확인

