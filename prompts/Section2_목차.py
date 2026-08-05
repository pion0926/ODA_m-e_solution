from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
목차 페이지 번호 슬롯은 LLM 생성 대상이 아니다.

[처리 규칙]
1. Section 2의 제목/목차 항목 구조는 원본 HWPX 양식을 그대로 유지한다.
2. 페이지 번호는 LLM이 추정하지 않는다.
3. 실제 페이지 번호는 최종 문서를 PDF로 변환한 뒤 알고리즘이 산출한 data/reports/toc_page_map.json 또는 data/reports/toc_source.pdf에서만 가져온다.
4. PDF/페이지맵이 없으면 페이지 번호 슬롯은 비워 두고 원본 양식의 값을 유지한다.
5. 작업 안내문 제거용 remove_page_notice만 빈 문자열로 둔다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록, 설명문, 주석, markdown은 쓰지 않는다.

{
  "schema": "section2_toc_slots_v1",
  "slots": {
    "remove_page_notice": "",
    "page_numbers": {}
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
