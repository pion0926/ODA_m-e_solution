from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 2. 일관성을 작성한다.

[참고할 입력]
- reference_corpus: 정책/전략 문서, 타 공여기관 사업, KOICA 포트폴리오, 사업 설계·수행 자료.
- content_inputs.criteria: 일관성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 내부 일관성(사업 설계 내부의 논리, 활동-산출-성과 연결)과 외부 일관성(수원국/KOICA/타 사업과의 연계)을 구분해 분석한다.
2. 평가질문이나 점수 라벨을 그대로 붙이지 말고, 보고서 문단으로 자연스럽게 작성한다.
3. 연계가 확인된 부분과 직접 근거가 제한적인 부분을 명확히 구분한다.
4. 다른 기준의 내용과 중복되면 일관성 관점으로 재정리한다.
5. 최종 본문만 반환한다.

[세부 판단 기준]
- 내적 일관성은 KOICA 타 사업, 국내 기관 사업, SDGs, 인권·젠더·환경 세이프가드, 국제규범, 사업 내부의 활동-산출-성과 논리를 함께 보고 판단한다.
- 높은 평가를 받은 경우에는 중복 또는 충돌이 없다는 표현에 그치지 말고, 어떤 기관·사업·규범과 어떤 방식으로 조정되어 시너지가 생겼는지 설명한다.
- 4점 수준의 판단은 국내 정책, KOICA 타 사업, 국제규범, 세이프가드 준수, 역할분담 근거가 모두 명확하고 중복 없이 부가가치가 확인될 때 작성한다.
- 3점 수준의 판단은 전반적 조화는 확인되나 구체적 조정회의, 역할분담, 세이프가드 적용 근거가 일부 제한될 때 작성한다.
- 외적 일관성은 타 공여기관, 수원국 정부, 현지 기관, 민간 주체와의 MoU, 조정회의록, RACI, 유사사업 맵을 보고 판단한다.
- 타 주체와의 조율은 중복 회피, 상호보완 역할, 공동 목표, 협의체 운영, 이슈 해소 기록이 확인되는 범위에서만 구체적으로 쓴다.

[출력]
일관성 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
