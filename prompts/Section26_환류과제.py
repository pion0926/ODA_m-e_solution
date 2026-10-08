from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
VI. 결론 3. 환류과제(제언)를 작성한다.

[참고할 입력]
- prior_analysis_sections: 결론, 작동요인, 비작동요인, 변화이론 분석을 1차 근거로 사용한다.
- content_inputs.criteria: 기준별 점수와 개선 필요 지점.
- reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 사업변경·운영관리·기자재·인력 관련 근거.
- sample_reference_for_this_section: 제언 표의 구분/제언/이해관계자 분리 방식과 문체.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 샘플 보고서의 제언 표처럼 구분, 제언, 이해관계자 중심으로 작성한다.
2. 구분은 사업모델 변경제언, 사업관리 개선제언, 개발환경 및 개입 특성상의 구조적 한계 분석 제언 중에서 고른다.
3. 제언은 관찰된 문제를 반복하지 말고 이해관계자가 실행할 수 있는 조치와 산출물로 쓴다.
4. 이해관계자는 실제 근거에 확인된 기관·부서로 구체화한다.
5. 각 항목은 반드시 '구분:', '제언:', '이해관계자:', '선정 사유:', '우선순위:', '완료기한:', '점검주기:', '후속 확인자료:' 필드를 이 순서로 포함한다.
6. 우선순위는 상/중/하, 완료기한은 YYYY-MM-DD 또는 검증 가능한 사업 단계, 점검주기는 월간/분기/반기 중 하나로 쓴다.
7. '아카데빙', '아카이빙' 대신 '기록·보관' 또는 '문서화'를 사용한다.
8. 근거 없는 과제나 일반론적 권고는 피하고, 앞선 분석 또는 참고 문서명/evidenceName에 기반해 작성한다.

[출력]
환류과제 최종 텍스트만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
