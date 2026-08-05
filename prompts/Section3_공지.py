from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
평가보고서 관련 공지 페이지의 placeholder 슬롯 값을 작성한다.

[참고할 입력]
- previous_text: 현재 공지 페이지 또는 이전 JSON 슬롯 값.
- content_inputs.project: 사업명, 기간, 예산 등 사업 기본 정보.
- reference_corpus: 평가책임자, 수행기관, 품질관리 관련 근거가 있을 때만 사용한다.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 원본 공지 문장 구조는 유지하고, placeholder 값만 작성한다.
2. 확인되지 않은 개인명, 소속, 날짜, 등급, 검토위원 정보는 "확인 중"로 쓴다.
3. 평가책임자/국가명/사업명처럼 사업개요에서 확인 가능한 값만 구체화한다.
4. 설명, 근거, XML, markdown은 쓰지 않는다.
5. 모든 값은 한 줄 문자열이어야 한다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section3_notice_slots_v1",
  "slots": {
    "responsible_evaluator_name_first": "확인 중",
    "country_name": "확인 중",
    "evaluated_project_name": "사업명 종료평가",
    "responsible_evaluator_name_second": "확인 중",
    "completion_date_value": "확인 중",
    "lead_evaluator_line": "책임평가자: 확인 중",
    "evaluation_expert_line": "평가 전문가: 확인 중",
    "sector_expert_line": "분야 전문가: 확인 중",
    "assistant_evaluator_line": "평가 보조원: 확인 중",
    "quality_review_date_value": "확인 중",
    "quality_grade_value": "확인 중",
    "review_chair_name": "확인 중",
    "review_member_1_name": "확인 중",
    "review_member_2_name": "확인 중",
    "review_member_3_name": "확인 중",
    "citation_lead": "확인 중"
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
