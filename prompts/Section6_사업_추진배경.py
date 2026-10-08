from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 6: II. 대상사업개요 - 1. 사업 추진배경의 기존 placeholder 양식을 유지하면서, 다섯 개 배경 문단의 텍스트만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 문단 수, 순서, 글꼴, 들여쓰기, XML 구조는 수정하지 않는다.
2. 단일 통합 본문 필드를 만들지 않는다. 아래 slots의 각 값이 원본 문서의 특정 배경 문단 하나를 대체한다.
3. 모든 slot 값은 반드시 `(소제목) 본문` 형식으로 시작한다. 변환기는 이를 최종 HWPX에서 `ㅇ (소제목)`과 다음 줄 본문으로 렌더링한다. `###`나 번호를 쓰지 않는다.
4. 각 slot 값은 문자열 하나이며 markdown, XML, 코드블록, 설명문을 넣지 않는다.
5. 미기재 안내 문구를 쓰지 말고 자료 기반 완성문으로 작성한다.
6. 자료가 충분하지 않아 보이는 항목도 reference_corpus, 사업개요서, 사전조사, PCP, PDM, 국별협력전략, 기준별 평가결과를 최대한 종합해 완성된 보고서 문단으로 쓴다.
7. 확인된 수치·연도·정책명은 적극 활용하되, 특정 수치가 불확실하면 수치 없이 정성적 문장으로 작성한다.
8. 샘플 보고서 문장은 복사하지 말고 현재 평가 대상 사업에 맞춰 새로 작성한다.
9. 첫 slot의 소제목은 국가정책 일반론보다 대상 사업의 핵심 개발문제에서 시작한다. 응급의료 사업이라면 `(우즈베키스탄 병원 전 응급의료 취약성과 구조적 문제)`처럼 구체화한다.
10. 최종 HWPX의 첫 줄은 `ㅇ (소제목)`이며 하위 근거는 `-` 수준이다. slot에는 `(소제목) 본문`만 제공하고, 본문 시작에 `ㅇ (다른 소제목)`을 다시 넣지 않는다. Markdown 굵게 기호로 slot 전체를 감싸지 않는다. 기호·들여쓰기·줄바꿈은 변환기가 처리한다.

[슬롯별 작성 기준]
- 슬롯명은 기존 HWPX와 연결되는 내부 식별자이며 현재 사업의 분야나 지원기관을 의미하지 않는다. 이름에 mdg_maternal_health 또는 koica가 있어도 모자보건 사업이나 KOICA 지원사업으로 추정하지 않는다.
- mdg_maternal_health_context: 현재 사업의 국가·분야별 핵심 개발문제, 격차, 서비스 접근성 문제.
- government_policy_context: 현재 사업 분야에 해당하는 협력국 정부 정책, 중기계획, 제도적 방향.
- target_region_need: 대상지역의 지리·사회경제적 취약성, 해당 분야 인프라와 역량 부족, 사업 요청 배경.
- koica_policy_alignment: 현재 사업 자료에서 확인된 실제 발주·지원기관의 정책, 개발목표, ODA 정책과의 부합성. KOICA가 확인되지 않으면 본문에 KOICA를 넣지 않는다. 확인되지 않은 전략명·기관 역할을 창작하지 않는다.
- project_selection_rationale: 왜 해당 사업이 신규 또는 후속 사업으로 추진되었는지에 대한 종합 판단.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section6_project_background_slots_v1",
  "slots": {
    "mdg_maternal_health_context": "(우즈베키스탄 병원 전 응급의료 취약성과 구조적 문제) ...",
    "government_policy_context": "(정부 정책과 제도적 방향) ...",
    "target_region_need": "(대상지역의 수요와 지원 필요성) ...",
    "koica_policy_alignment": "(ODA 정책 및 지원전략과의 정합성) ...",
    "project_selection_rationale": "(사업 선정과 형성 논리) ..."
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
