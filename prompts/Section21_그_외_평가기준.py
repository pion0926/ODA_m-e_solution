from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 7. 그 외 평가기준을 작성한다.

[참고할 입력]
- reference_corpus: 위 기준으로 포착되지 않는 특수 이슈, 혁신성, 확장성, 위험관리 등 관련 근거.
- prior_analysis_sections: 앞선 기준별 분석.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 실제로 의미 있는 추가 관점이나 특수 이슈가 있을 때만 작성한다.
2. 이 절은 DAC 점수에 합산하지 않는 비채점 보완 관점이다. "DAC 6대 기준", "별도 핵심 평가기준"처럼 공식 평가기준으로 승격하지 않는다.
3. 쓸 내용이 없으면 억지로 새 기준을 만들지 말고, 해당 사항이 제한적임을 짧게 정리한다.
4. 앞 기준의 반복은 피하고, 추가적으로 보고서에 필요한 판단만 담는다.
5. 최종 보고서 본문으로 작성한다.

[출력]
그 외 평가기준 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
