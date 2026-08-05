from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = "[작성 대상]\nVI. 결론 3. 교훈을 작성한다.\n\n[참고할 입력]\n- prior_analysis_sections: 작동요인, 비작동요인, 환류과제, 변화이론 분석, 결론을 1차 근거로 사용한다.\n- content_inputs.criteria: 기준별 평가결과와 개선 필요 지점.\n- reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 운영관리·기자재·인력 관련 근거.\n- sample_reference_for_this_section: 작동요인/비작동요인에서 교훈을 도출하는 방식과 문체.\n- previous_text: 현재 양식과 문체.\n- user_request: 사용자가 직접 입력한 수정 요청.\n\n[작성 규칙]\n1. 작동요인은 확산 가능한 설계·수행 원칙으로, 비작동요인은 사전 점검·위험관리 교훈으로 전환한다.\n2. 특정 사건 나열로 끝내지 말고 후속 유사 사업에서 재사용할 수 있는 판단 기준으로 쓴다.\n3. 각 항목은 반드시 '교훈 N. (관찰사항 제목)', '교훈 내용:', '분야/일반 구분:', '이전년도 교훈 중복 여부:', '체크리스트 질문:' 필드를 포함한다.\n4. 분야/일반 구분에는 일반 또는 분야만 쓰고, 이전년도 교훈 중복 여부에는 신규 또는 중복(연도/분야)처럼 짧게 쓴다.\n5. 체크리스트 질문은 M&E 단계에서 바로 점검 가능한 질문 1문장으로 쓴다.\n6. 샘플 문장을 복사하지 말고 현재 사업의 앞선 분석과 참고자료를 종합해 새로 작성한다.\n\n[출력]\n교훈 최종 텍스트만 반환한다."


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
