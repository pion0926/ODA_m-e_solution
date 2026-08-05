from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 8: II. 대상사업개요 - 3. 사업설계매트릭스(PDM) 표의 placeholder 셀만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 표, 행/열, 병합, 글꼴, XML 구조는 절대 수정하지 않는다.
2. 아래 slots의 각 값은 원본 PDM 표의 특정 셀 하나를 대체한다.
3. markdown 표, XML, HTML, 코드블록, 설명문을 쓰지 않는다.
4. 각 값은 셀 안에 들어갈 최종 텍스트만 작성한다.
5. 줄바꿈이 필요한 항목은 " / "로 구분한다. <br> 태그를 쓰지 않는다.
6. 한 셀은 가능한 1~4개 짧은 항목으로 압축한다. 긴 설명문을 쓰지 않는다.
7. 자료가 직접 부족해도 PDM, 사업개요서, 성과지표 실적표, reference_corpus를 종합해 최대한 작성한다.

[PDM 표 구조]
- 영향(Impact): impact_summary, impact_indicator, impact_mov, impact_assumption
- 성과(Outcome): outcome_summary, outcome_indicator, outcome_mov, outcome_assumption
- 산출물(Outputs): outputs_summary, outputs_indicator, outputs_mov, outputs_assumption
- 활동/투입/전제조건: activities, inputs, preconditions

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section8_pdm_slots_v1",
  "slots": {
    "impact_summary": "...",
    "impact_indicator": "...",
    "impact_mov": "...",
    "impact_assumption": "...",
    "outcome_summary": "...",
    "outcome_indicator": "...",
    "outcome_mov": "...",
    "outcome_assumption": "...",
    "outputs_summary": "...",
    "outputs_indicator": "...",
    "outputs_mov": "...",
    "outputs_assumption": "...",
    "activities": "...",
    "inputs": "...",
    "preconditions": "..."
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
