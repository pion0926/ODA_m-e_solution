from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 5: I. 평가결과 요약 - 1. 국문 요약의 기존 placeholder 구조를 유지하면서, 각 입력 문단의 텍스트만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 문단 수, 순서, 글꼴, 표, XML 구조는 수정하지 않는다.
2. 단일 통합 요약 필드를 만들지 않는다. 아래 slots의 각 값이 원본 문서의 특정 문단 하나를 대체한다.
3. 기존 구조 표지를 값 안에 그대로 포함한다. 예: "가. 사업명 :", "ㅇ 추진배경", "- (평가목적)", "ㅇ 결론".
4. 각 slot 값은 문자열 하나이며 markdown, XML, 코드블록, 설명문을 넣지 않는다.
5. 미기재 안내 문구를 쓰지 말고 자료 기반 완성문으로 작성한다.
6. 정보가 직접적으로 부족해도 reference_corpus, content_inputs, prior_analysis_sections, criteria 평가결과, 사업개요/PDM/평가매트릭스/등급표를 최대한 종합해 가장 개연성 높은 보고서 문장으로 완성한다.
7. 불확실한 수치가 있으면 수치 없이 정성적으로 쓴다. 확인되지 않은 개인명만 피하고, 사업 배경·성과·평가판단은 주어진 자료 범위에서 합리적으로 요약한다.
8. 샘플 보고서 문장은 복사하지 말고 현재 평가 대상 사업에 맞춰 새로 작성한다.

[슬롯별 작성 기준]
- project_name_line: "가. 사업명 : 사업명(기간/예산)" 한 줄.
- business_background: 사업 필요성/추진배경을 "- ..." 한 문단으로 작성.
- business_overview: 사업개요를 "- (사업개요) ..." 한 문단으로 작성.
- evaluation_purpose: "- (평가목적) ..." 형식.
- evaluation_scope: "- (평가범위) ..." 형식.
- evaluation_method_overview: "ㅇ 평가방법: ..." 형식으로 방법 목록 요약.
- document_review_method: "- (문헌조사) ..." 형식.
- stakeholder_interview_method: "- (이해관계자 인터뷰) ..." 형식.
- field_survey_method: "- (현지실사) ..." 형식.
- evaluation_limitations: "ㅇ 평가의 한계: ..." 형식.
- achievement_summary: 성과 달성도 요약을 "ㅇ ..." 한 문단.
- relevance_summary/coherence_summary/effectiveness_summary/efficiency_summary/sustainability_summary: 기준별 평가 결과를 각각 "- ..." 한 문단.
- crosscutting_human_rights_gender: "- (인권 및 성 주류화) ..." 형식.
- crosscutting_environment: "- (환경영향) ..." 형식.
- conclusion_goal_achievement: "- (사업 목표 달성) ..." 형식.
- conclusion_dac_results: "- (DAC 6대 기준에 따른 평가결과) ..." 형식.
- conclusion_crosscutting_results: "- (범 분야 이슈 평가 결과) ..." 형식.
- lesson_working_factors: "- (작동요인) ..." 형식.
- lesson_nonworking_factors: "- (비작동요인) ..." 형식.
- recommendation_project_model: "- (사업모델 변경제언) ..." 형식.
- recommendation_project_management: "- (사업관리 개선제언) ..." 형식.
- recommendation_structural_limits: "- (개발환경 및 개입 특성상의 구조적 한계 분석 제언) ..." 형식.
- recommendation_other: "- (기타) ..." 형식.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section5_summary_slots_v1",
  "slots": {
    "project_name_line": "가. 사업명 : ...",
    "business_background": "- ...",
    "business_overview": "- (사업개요) ...",
    "evaluation_purpose": "- (평가목적) ...",
    "evaluation_scope": "- (평가범위) ...",
    "evaluation_method_overview": "ㅇ 평가방법: ...",
    "document_review_method": "- (문헌조사) ...",
    "stakeholder_interview_method": "- (이해관계자 인터뷰) ...",
    "field_survey_method": "- (현지실사) ...",
    "evaluation_limitations": "ㅇ 평가의 한계: ...",
    "achievement_summary": "ㅇ ...",
    "relevance_summary": "- ...",
    "coherence_summary": "- ...",
    "effectiveness_summary": "- ...",
    "efficiency_summary": "- ...",
    "sustainability_summary": "- ...",
    "crosscutting_human_rights_gender": "- (인권 및 성 주류화) ...",
    "crosscutting_environment": "- (환경영향) ...",
    "conclusion_goal_achievement": "- (사업 목표 달성) ...",
    "conclusion_dac_results": "- (DAC 6대 기준에 따른 평가결과) ...",
    "conclusion_crosscutting_results": "- (범 분야 이슈 평가 결과) ...",
    "lesson_working_factors": "- (작동요인) ...",
    "lesson_nonworking_factors": "- (비작동요인) ...",
    "recommendation_project_model": "- (사업모델 변경제언) ...",
    "recommendation_project_management": "- (사업관리 개선제언) ...",
    "recommendation_structural_limits": "- (개발환경 및 개입 특성상의 구조적 한계 분석 제언) ...",
    "recommendation_other": "- (기타) ..."
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
