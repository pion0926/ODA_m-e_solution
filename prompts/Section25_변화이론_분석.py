from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = "[작성 대상]\nVI. 결론 2. 변화이론 분석을 작성한다.\n\n[참고할 입력]\n- reference_corpus: 사업 설계, PDM, 성과자료, 평가결과, 인터뷰 등 변화 경로 검토 근거.\n- prior_analysis_sections: 사업개요, 성과달성도, 기준별 평가결과, 작동/비작동요인.\n- previous_text: 현재 양식과 문체.\n- user_request: 사용자가 직접 입력한 수정 요청.\n\n[작성 규칙]\n1. 투입-활동-산출-성과-영향의 변화 경로를 정리하고, 각 단계가 어떻게 연결되었는지 분석한다.\n2. 설계 당시의 핵심 가정이 실제 수행에서 유지되었는지 또는 약화되었는지 설명한다.\n3. 단순 PDM 재작성에 그치지 말고, 평가결과를 바탕으로 변화 경로의 강점과 단절 지점을 분석한다.\n4. 확인되지 않은 영향은 단정하지 않는다.\n5. 최종 보고서 본문으로 작성한다.\n\n[출력]\n변화이론 분석 최종 본문만 반환한다."


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
