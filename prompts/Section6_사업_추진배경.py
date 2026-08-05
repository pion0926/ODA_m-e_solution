from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 6: II. 대상사업개요 - 1. 사업 추진배경의 기존 placeholder 양식을 유지하면서, 다섯 개 배경 문단의 텍스트만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 문단 수, 순서, 글꼴, 들여쓰기, XML 구조는 수정하지 않는다.
2. 단일 통합 본문 필드를 만들지 않는다. 아래 slots의 각 값이 원본 문서의 특정 `ㅇ` 문단 하나를 대체한다.
3. 모든 slot 값은 반드시 `ㅇ `로 시작한다.
4. 각 slot 값은 문자열 하나이며 markdown, XML, 코드블록, 설명문을 넣지 않는다.
5. 미기재 안내 문구를 쓰지 말고 자료 기반 완성문으로 작성한다.
6. 자료가 충분하지 않아 보이는 항목도 reference_corpus, 사업개요서, 사전조사, PCP, PDM, 국별협력전략, 기준별 평가결과를 최대한 종합해 완성된 보고서 문단으로 쓴다.
7. 확인된 수치·연도·정책명은 적극 활용하되, 특정 수치가 불확실하면 수치 없이 정성적 문장으로 작성한다.
8. 샘플 보고서 문장은 복사하지 말고 현재 평가 대상 사업에 맞춰 새로 작성한다.

[슬롯별 작성 기준]
- mdg_maternal_health_context: 국가/분야 배경, 보건·모자보건 문제, 격차, 서비스 접근성 문제.
- government_policy_context: 협력국 정부의 보건·모자보건 정책, 중기계획, 제도적 방향.
- target_region_need: 대상지역의 지리·사회경제적 취약성, 보건의료 인프라 부족, 사업 요청 배경.
- koica_policy_alignment: KOICA 국가/분야 전략, 개발목표, ODA 정책과의 부합성.
- project_selection_rationale: 왜 해당 사업이 신규 또는 후속 사업으로 추진되었는지에 대한 종합 판단.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section6_project_background_slots_v1",
  "slots": {
    "mdg_maternal_health_context": "ㅇ ...",
    "government_policy_context": "ㅇ ...",
    "target_region_need": "ㅇ ...",
    "koica_policy_alignment": "ㅇ ...",
    "project_selection_rationale": "ㅇ ..."
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
