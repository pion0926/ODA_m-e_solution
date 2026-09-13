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
2. authoritative_pdm에 지정된 최신 PDM 1건을 지표 명칭·계층·MOV의 유일한 설계 기준으로 사용한다. 원안·1차 수정 PDM이나 과거 연차계획의 지표를 섞지 않는다.
3. 최신 PDM의 Outcome 및 Output 지표를 누락 없이 모두 작성한다. 대표 3~5개로 축약하지 않는다. Impact는 Section 8 PDM에만 두고 본 성과표의 평가대상 행으로 만들지 않는다.
4. 최신 PDM에 목표치가 없으면 과거 PDM 목표를 가져오지 말고 "최신 PDM 미기재"라고 명확히 쓴다. 실적은 최신 성과실적 자료에서 같은 지표가 직접 매칭될 때만 사용한다.
5. "추가 정보 필요", "자료 없음" 같은 포괄적 안내문을 쓰지 않는다. 확인되지 않은 수치를 정성 표현으로 덮거나 창작하지 않는다.
6. 지표별로 목표, 실적, 달성 여부, 확인 근거, 미달 또는 초과 사유를 간결히 쓴다.
7. '평가점수 2/4' 같은 점수 라벨을 쓰지 않는다.
8. HWPX 행 파서가 읽을 수 있는 아래 라벨 형식 또는 동일 필드의 Markdown 표를 사용한다. XML, 코드블록, 불필요한 장문 해설은 쓰지 않는다.

[세부 생성 기준]
- 최신 PDM은 지표 목록과 MOV의 최상위 권위이며, 승인된 최신 성과관리 자료는 동일 지표의 목표·실적을 보완하는 2순위 근거다.
- 각 항목은 기초선, 목표치, 종료선 또는 현재 실적, 지표입증수단(MOV), 확인 문서를 기준으로 작성한다.
- 달성 여부는 단순히 "달성"이라고 쓰지 말고, 목표 대비 실적의 차이와 그 차이가 산출물·성과 판단에 미치는 의미를 함께 쓴다.
- 수치가 없는 지표는 종료보고서, 성과점검 보고서, 현장확인, 인터뷰 등 정성 근거로 대체하되 불확실성을 숨기지 않는다.
- 미달성 또는 초과 달성은 지연, 외부환경, 예산·조달, 운영역량, 수요 변화 등 확인된 원인을 연결하여 작성한다.

[출력 형식]
표 매핑 레코드와 독자용 해설의 역할을 구분한다. 비고에는 해당 지표의 핵심 진척·해석·한계·후속 확인사항을 간결한 개조식으로 작성한다. 변환기는 레코드의 수치를 표에 넣고 비고를 성과(Outcome)/산출물(Output)별 해설로 표시한다. 본문 해설에 지표 ID, 동일한 지표명 반복, 기초선/목표치/실적을 슬래시로 나열하는 문장을 추가하지 않는다. 문장 종결은 ~함/~음으로 통일한다.
아래 라벨 형식으로 최신 PDM의 Outcome·Output 지표 전체를 작성한다. 각 항목은 빈 줄로 구분한다.

- [PDM 지표 코드와 명칭]: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선 또는 현재 실적: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
- 문서명·페이지·표·추출 항목은 사실 검증에만 사용하고 최종 문장과 표 셀에는 괄호 인용으로 넣지 않는다.
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
