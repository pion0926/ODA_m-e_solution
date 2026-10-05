from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
첫 페이지 표지의 5개 슬롯만 작성한다.

[유일한 사실 입력]
content_inputs.project에 전달된 현재 사업 기본정보만 사용한다.
사업 기본정보의 근거는 현재 명시적으로 등록된 사업계획서다.
project.title은 사업명, project.project_manager는 사업책임자,
project.lead_implementer는 주관 수행기관이며 report_context.draft_date는 작성 기준연월이다.
PDM, 일반 업로드, 과거 자체평가서, 선행 보고서, 평가자 위촉 문서와 previous_text에서 인물·기관을 가져오지 않는다.

[작성 규칙]
1. project_title은 project.title을 그대로 사용한다. 세부 과업명이나 예산 항목명으로 바꾸지 않는다.
2. report_title은 "종료평가 결과보고서"다. 사업 종료 여부를 표지에서 추정하지 않는다.
3. report_date는 작성 기준연월을 YYYY. MM 형식으로 표시한다.
4. evaluation_manager는 기존 양식의 슬롯 ID이며 값은 "사업책임자 " + project.project_manager다.
5. evaluation_institution도 기존 슬롯 ID이며 값은 "사업 수행기관 " + project.lead_implementer다.
6. 사업 담당자를 평가자로 재명명하지 않는다. 사업 기본정보에 없는 사람·기관은 "확인 필요"로 표시한다.
7. 이전 표지의 잘못된 평가자 정보는 유지하지 않는다. 이름을 수정하려면 사업 기본정보를 먼저 수정한다.
8. 모든 값은 한 줄이다. 본문, 근거 설명, 문서명, 연락처, 연구자번호, 로고, XML은 출력하지 않는다.

[출력 형식]
다음 JSON 객체 하나만 반환한다.
{
  "schema": "section1_cover_slots_v1",
  "slots": {
    "project_title": "사업 기본정보의 사업명",
    "report_title": "종료평가 결과보고서",
    "report_date": "YYYY. MM",
    "evaluation_manager": "사업책임자 확인 필요",
    "evaluation_institution": "사업 수행기관 확인 필요"
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
