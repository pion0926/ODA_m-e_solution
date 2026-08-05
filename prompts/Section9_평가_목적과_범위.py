from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 9: III. 평가개요 - 1. 평가의 목적과 범위의 본문 슬롯만 작성한다.

[작성 규칙]
1. 원본 HWPX의 제목과 양식은 수정하지 않는다.
2. evaluation_purpose_scope_body에 들어갈 최종 본문만 작성한다.
3. 평가 목적, 활용 주체, 평가 대상, 평가 범위, 기준, 기간, 결과 활용 계획을 공식 보고서 문체로 정리한다.
4. 평가방법 상세 내용은 Section 11에서 다루므로 여기서는 범위 수준으로만 언급한다.
5. markdown, XML, 설명문, 인접 섹션 내용은 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다.

{
  "schema": "section9_eval_purpose_slots_v1",
  "slots": {
    "evaluation_purpose_scope_body": "평가 목적과 범위 본문"
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
