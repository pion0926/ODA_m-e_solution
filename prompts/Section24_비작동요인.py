from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = "[작성 대상]\nVI. 결론 2. 비작동요인을 작성한다.\n\n[참고할 입력]\n- prior_analysis_sections: 성과달성도와 기준별 평가결과.\n- reference_corpus: 지연, 미달, 운영상 제약, 설계상 한계 관련 근거.\n- previous_text: 현재 양식과 문체.\n- user_request: 사용자가 직접 입력한 수정 요청.\n\n[작성 규칙]\n1. 비작동요인은 사업 성과를 제한한 설계·수행·환경 요인을 정리한다.\n2. 책임 추궁식 표현보다 개선 가능한 구조적 원인 중심으로 쓴다.\n3. 앞 섹션에서 확인된 한계와 연결하되, 같은 문장을 반복하지 않는다.\n4. 근거 없는 비판은 쓰지 않는다.\n5. 최종 보고서 본문으로 작성한다.\n\n[출력]\n비작동요인 최종 본문만 반환한다."


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
