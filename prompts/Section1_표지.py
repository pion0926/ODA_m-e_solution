from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
보고서 표지에 들어갈 슬롯 값을 작성한다.

[참고할 입력]
- previous_text: 현재 표지에 표시된 기존 문구 또는 이전 JSON 슬롯 값. 평가책임자와 평가수행기관이 이미 확정되어 있으면 유지한다.
- content_inputs.project: 사업명, 기간, 예산, 개요 문서명 등 표지 판단에 필요한 최소 정보.
- report_context.draft_date: 표지 기준 연월.
- user_request: 사용자가 직접 입력한 수정 요청. 다른 입력보다 우선한다.

[작성 규칙]
1. 표지는 아래 5개 슬롯만 작성한다.
   - project_title
   - report_title
   - report_date
   - evaluation_manager
   - evaluation_institution
2. project_title은 content_inputs.project.title을 우선 사용한다.
3. report_title은 report_context의 검증된 사업상태를 따른다. 종료 사업은 "종료평가 결과보고서", 진행 중 사업은 "현시점 평가보고서"로 쓴다.
4. report_date는 YYYY. MM 형식으로 쓴다.
5. evaluation_manager는 서명된 평가·자체평가 보고서의 확인자/평가총괄을 우선 근거로 삼아 "평가책임자 "로 시작한다. 사업 수행기관명만으로 사람을 추정하지 않는다.
6. evaluation_institution은 같은 평가 보고서의 제출기관·발간기관을 우선 근거로 삼아 "평가수행기관 "으로 시작한다. 일반 사업개요의 수행기관만으로 추정하지 않는다.
7. verified_execution_scope에 평가책임자·평가수행기관이 확인되면 그 값을 그대로 사용한다. 확인되지 않은 값을 창작하지 않는다.
8. 모든 슬롯 값은 한 줄 문자열이어야 한다. 줄바꿈, markdown, XML, 설명, 근거, 파일명은 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section1_cover_slots_v1",
  "slots": {
    "project_title": "사업명",
    "report_title": "검증된 평가유형 평가보고서",
    "report_date": "YYYY. MM",
    "evaluation_manager": "평가책임자 확인 중",
    "evaluation_institution": "평가수행기관 확인 중"
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
