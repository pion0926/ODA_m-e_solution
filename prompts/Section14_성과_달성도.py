from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
IV. 성과 달성도 표에 들어갈 성과지표별 내용을 작성한다.

[참고할 입력]
- reference_corpus: PDM, 성과지표, 산출물 실적, 종료보고서, 점검표, 인터뷰/설문 근거.
- content_inputs.criteria: 성과달성도 관련 기준과 점수.
- previous_text: 현재 성과달성도 표 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 표 셀로 분해될 수 있도록 항목별 라벨 형식을 반드시 지킨다.
2. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 수치가 불확실하면 정성적 표현으로 대체한다.
3. 지표별로 목표, 실적, 달성 여부, 확인 근거, 미달 또는 초과 사유를 간결히 쓴다.
4. '평가점수 2/4' 같은 점수 라벨을 쓰지 않는다.
5. markdown table, XML, 코드블록, 장문 해설은 쓰지 않는다.

[세부 생성 기준]
- 최신 PDM 또는 승인된 성과관리 자료를 우선 사용하고, 지표가 변경된 경우 변경 전후 지표를 혼합하지 않는다.
- 각 항목은 기초선, 목표치, 종료선 또는 현재 실적, 지표입증수단(MOV), 확인 문서를 기준으로 작성한다.
- 달성 여부는 단순히 "달성"이라고 쓰지 말고, 목표 대비 실적의 차이와 그 차이가 산출물·성과 판단에 미치는 의미를 함께 쓴다.
- 수치가 없는 지표는 종료보고서, 성과점검 보고서, 현장확인, 인터뷰 등 정성 근거로 대체하되 불확실성을 숨기지 않는다.
- 미달성 또는 초과 달성은 지연, 외부환경, 예산·조달, 운영역량, 수요 변화 등 확인된 원인을 연결하여 작성한다.

[출력 형식]
아래 형식으로 3~5개 항목을 작성한다. 각 항목은 빈 줄로 구분한다.

- 군립병원 인프라 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
- 보건의료 인력 역량 강화: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
- 지역사회 모자보건 서비스 이용 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
