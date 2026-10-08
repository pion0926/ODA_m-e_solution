from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
목차 페이지 번호 슬롯은 LLM 생성 대상이 아니다.

[처리 규칙]
1. Section 2의 제목/목차 항목 구조는 원본 HWPX 양식을 그대로 유지하되 report_sections의 실제 장·절 순서와 일치시킨다.
2. "영향" 또는 "파급효과"를 별도 DAC 평가기준 장·절로 추가하지 않는다.
3. 평가매트릭스 번호는 "2. 평가매트릭스"로 고정한다.
4. 페이지 번호는 LLM이 추정하지 않는다.
5. 실제 페이지 번호는 1차 HWPX를 Kordoc/rhwp로 조판한 뒤 페이지별 텍스트에서 알고리즘이 산출하고, 같은 HWPX에 2차 반영한다.
6. 페이지 번호 노드에는 공백·탭·장식문자를 넣지 않고 공백 없는 정수만 기록하며, 모든 세부 목차 행은 같은 우측 페이지 번호 열을 사용한다. 이 처리는 HWPX 변환 모듈이 담당한다.
7. 작업 안내문 제거용 remove_page_notice만 빈 문자열로 둔다.

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
