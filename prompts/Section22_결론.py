from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = "[작성 대상]\nVI. 결론 1. 결론을 작성한다.\n\n[참고할 입력]\n- prior_analysis_sections: 앞서 작성된 사업개요, 평가개요, 성과달성도, 기준별 평가결과.\n- content_inputs.criteria: 기준별 점수와 핵심 판단.\n- reference_corpus: 결론 검증에 필요한 제한적 원문 근거.\n- previous_text: 현재 양식과 문체.\n- user_request: 사용자가 직접 입력한 수정 요청.\n\n[작성 규칙]\n1. 결론은 원문을 처음부터 다시 분석하는 글이 아니라, 앞 섹션의 판단을 종합하는 글이다.\n2. 사업의 의의, 주요 성과, 핵심 제약, 종합 평가를 균형 있게 정리한다.\n3. 새로운 사실이나 새로운 점수를 만들지 않는다.\n4. 기준별 내용을 단순 반복하지 말고, 보고서 전체 메시지가 드러나게 쓴다.\n5. 최종 보고서 본문만 반환한다.\n\n[출력]\n결론 최종 본문만 반환한다."


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
