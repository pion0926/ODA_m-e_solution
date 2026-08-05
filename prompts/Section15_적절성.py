from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 1. 적절성 본문을 작성한다.

[참고할 입력]
- reference_corpus: 사업요청서, PCP, 정책문서, 수요조사, 설계자료, 인터뷰 등 적절성 판단 근거.
- content_inputs.criteria: 적절성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 세부 항목별 소제목을 두고, 각 항목은 최종 보고서 문체의 줄글 중심으로 분석한다.
2. 평가질문을 그대로 반복하거나 '평가점수 2/4'처럼 쓰지 않는다. 점수는 판단의 배경으로만 자연스럽게 반영한다.
3. 사업이 대상 지역 수요, 수원국 정책, KOICA 전략, 대상자 요구와 얼마나 부합했는지 근거 기반으로 설명한다.
4. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 자료가 부족하면 제공 자료에서 확인되는 범위와 해석 한계를 문장 안에 녹인다.
5. 긍정 근거와 보완점을 균형 있게 쓰고, 샘플 문장은 복사하지 않는다.
6. markdown table, XML, 코드블록, 파일 경로는 쓰지 않는다.

[세부 판단 기준]
- 정책·수요·우선순위 반영 여부는 협력국 국가개발전략 또는 부문별 정책, 한국 정부/KOICA CPS·CAS, 사전조사 및 기초조사, PCP/RD, 최신 PDM, ToC·문제나무, 수혜자·이해관계자 수요조사 자료를 함께 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 정책에 부합한다고 쓰지 말고, 정책 방향, 지역·수혜자 수요, 사업 산출물, PDM 지표, 변화이론이 어떤 논리로 연결되었는지 구체적으로 설명한다.
- 4점 수준의 판단은 협력국 정책과 KOICA 전략 부합, 사전 수요조사, 현지 이해관계자 참여, 문제나무 또는 ToC 기반 설계, 우선순위의 PDM 반영이 모두 확인될 때 작성한다.
- 3점 수준의 판단은 정책·수요와 대체로 부합하나 현지 참여, 취약계층 수요, 분석방식, PDM 연결근거 중 일부가 충분히 입증되지 않을 때 작성한다.
- 상황변화 대응 여부는 정기 모니터링, 사업변경 요청, 운영위원회/JSC 회의록, 리스크 대응 기록, 변경 PDM, 일정·예산 변경 자료를 보고 판단한다.
- 외부 변화가 있었던 경우에는 변화의 내용, 사업의 대응 시점, 이해관계자 조정, 대안의 실행 가능성, 성과지표 달성에 미친 영향을 함께 설명한다.

[출력]
적절성 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
