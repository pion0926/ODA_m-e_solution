# 평가보고서 27×27 독립 모듈 구조

## 동작 원칙

- 생성 단계의 원본은 `prompts/Section*.py` 27개이며, 각 파일의 `EDITOR_PROMPT`와 `build_prompt_input()`을 독립적으로 수정·실행할 수 있다.
- HWPX/rHWP 변환 단계의 원본은 `redesign/backend/kodame_intake/hwpx_adapters/sections/section*.py` 27개이며, 각 파일이 계약·정규화·구조화 준비·XML 반영 진입점을 독립적으로 가진다.
- `hwpx_adapters/registry.py`는 파일을 순서대로 등록하고 호출만 한다. 섹션별 작성 규칙이나 XML 치환 구현을 중앙 분기문에 두지 않는다.
- 공통 XML 유틸리티, 문단 정규화, 표 셀 조작은 공유하되 어느 공유 함수를 어떤 순서로 호출할지는 각 섹션 파일이 결정한다.
- DB의 `report_sections.content`가 생성 초안과 HWPX의 단일 원본이다. 변환 단계는 새 사실을 생성하지 않는다.

## 27개 독립 파일 대응표

| 번호 | part_id | 생성 프롬프트 | HWPX/rHWP 변환 모듈 |
|---:|---|---|---|
| 1 | cover | `prompts/Section1_표지.py` | `hwpx_adapters/sections/section01_cover.py` |
| 2 | toc | `prompts/Section2_목차.py` | `hwpx_adapters/sections/section02_toc.py` |
| 3 | notice | `prompts/Section3_공지.py` | `hwpx_adapters/sections/section03_notice.py` |
| 4 | grade | `prompts/Section4_평가등급_결과표.py` | `hwpx_adapters/sections/section04_grade.py` |
| 5 | summary-ko | `prompts/Section5_국문_요약.py` | `hwpx_adapters/sections/section05_summary_ko.py` |
| 6 | project-background | `prompts/Section6_사업_추진배경.py` | `hwpx_adapters/sections/section06_project_background.py` |
| 7 | project-overview | `prompts/Section7_사업개요.py` | `hwpx_adapters/sections/section07_project_overview.py` |
| 8 | pdm | `prompts/Section8_PDM.py` | `hwpx_adapters/sections/section08_pdm.py` |
| 9 | eval-purpose | `prompts/Section9_평가_목적과_범위.py` | `hwpx_adapters/sections/section09_eval_purpose.py` |
| 10 | eval-matrix | `prompts/Section10_평가매트릭스.py` | `hwpx_adapters/sections/section10_eval_matrix.py` |
| 11 | eval-methods | `prompts/Section11_평가방법.py` | `hwpx_adapters/sections/section11_eval_methods.py` |
| 12 | eval-limitations | `prompts/Section12_평가의_한계.py` | `hwpx_adapters/sections/section12_eval_limitations.py` |
| 13 | eval-team | `prompts/Section13_평가팀_구성_및_시행체계.py` | `hwpx_adapters/sections/section13_eval_team.py` |
| 14 | achievement | `prompts/Section14_성과_달성도.py` | `hwpx_adapters/sections/section14_achievement.py` |
| 15 | criteria-relevance | `prompts/Section15_적절성.py` | `hwpx_adapters/sections/section15_criteria_relevance.py` |
| 16 | criteria-coherence | `prompts/Section16_일관성.py` | `hwpx_adapters/sections/section16_criteria_coherence.py` |
| 17 | criteria-effectiveness | `prompts/Section17_효과성.py` | `hwpx_adapters/sections/section17_criteria_effectiveness.py` |
| 18 | criteria-efficiency | `prompts/Section18_효율성.py` | `hwpx_adapters/sections/section18_criteria_efficiency.py` |
| 19 | criteria-sustainability | `prompts/Section19_지속가능성.py` | `hwpx_adapters/sections/section19_criteria_sustainability.py` |
| 20 | criteria-crosscutting | `prompts/Section20_범분야_이슈.py` | `hwpx_adapters/sections/section20_criteria_crosscutting.py` |
| 21 | criteria-other | `prompts/Section21_그_외_평가기준.py` | `hwpx_adapters/sections/section21_criteria_other.py` |
| 22 | conclusion | `prompts/Section22_결론.py` | `hwpx_adapters/sections/section22_conclusion.py` |
| 23 | working-factors | `prompts/Section23_작동요인.py` | `hwpx_adapters/sections/section23_working_factors.py` |
| 24 | nonworking-factors | `prompts/Section24_비작동요인.py` | `hwpx_adapters/sections/section24_nonworking_factors.py` |
| 25 | theory | `prompts/Section25_변화이론_분석.py` | `hwpx_adapters/sections/section25_theory.py` |
| 26 | feedback | `prompts/Section26_환류과제.py` | `hwpx_adapters/sections/section26_feedback.py` |
| 27 | lessons | `prompts/Section27_교훈.py` | `hwpx_adapters/sections/section27_lessons.py` |

HWPX 변환 모듈의 표 경로는 위 표에서 공통 접두사 `redesign/backend/kodame_intake/`를 생략했다.

## 섹션 수정 방법

예를 들어 평가등급 결과표를 수정할 때는 다음 두 파일만 우선 수정한다.

1. 내용 생성 형식·제약: `prompts/Section4_평가등급_결과표.py`
2. HWPX 표 셀·행 조판 진입점: `redesign/backend/kodame_intake/hwpx_adapters/sections/section04_grade.py`

공통 표 행 높이나 XML 셀 조작 자체를 바꿔야 할 때만 `backend/oda_me/hwpx/patchers.py` 또는 `hwpx_layout/`의 공유 유틸리티를 수정한다. 이렇게 하면 다른 26개 섹션에 미치는 영향을 명확하게 추적할 수 있다.

## 자동 계약 검증

- `test_report_section_contracts.py`는 27개 프롬프트 파일 경로와 27개 변환 모듈 경로가 모두 서로 다른지 검사한다.
- 각 변환 모듈의 `normalize`, `prepare`, `patch_xml` 함수가 그 모듈 자체에 정의되어 있는지 검사한다.
- `tools/report_prompt_audit.py`는 각 섹션별 프롬프트 원본과 변환 원본 경로를 결과 보고서에 기록하고, 중복 경로가 있으면 실패한다.
