from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
III. 평가개요 4. 평가의 한계 본문을 작성한다.

[참고할 입력]
- reference_corpus: 미확보 자료, 인터뷰 제약, 조사 범위 제한, 데이터 품질 관련 근거.
- content_inputs.criteria: 기준별 자료 충분성 및 한계.
- prior_analysis_sections: 이미 작성된 분석에서 확인된 공백.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 한계는 "제약 내용 - 분석 영향 - 보완 방식"이 드러나도록 작성한다.
2. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다.
3. 자료가 부족한 경우에도 제공 자료에서 확인되는 데이터 공백, 현장 접근성, 성과지표 추적 한계, 이해관계자 기억 의존성 등을 평가 한계로 구체화한다.
4. 책임 회피가 아니라 해석 범위를 명확히 하는 톤으로 작성한다.
5. 표, markdown, XML, 코드블록 없이 최종 보고서 본문만 작성한다.

[출력]
평가의 한계 최종 텍스트만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
