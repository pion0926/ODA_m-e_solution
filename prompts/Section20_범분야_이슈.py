from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 6. 범분야 이슈를 작성한다.

[참고할 입력]
- reference_corpus: 성평등, 환경, 인권, 취약계층, 세이프가드, 갈등민감성 관련 근거.
- content_inputs.criteria: 범분야 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 자료에서 확인되는 범분야 이슈만 작성한다.
2. 성평등, 환경, 취약계층, 인권, 세이프가드 항목을 억지로 모두 채우지 않는다.
3. 확인되지 않는 항목은 '확인 가능한 근거가 제한적임' 정도로 간결히 처리한다.
4. 사업 설계와 수행에서 실제로 어떻게 반영되었는지, 부족한 점은 무엇인지 분석한다.
5. 최종 보고서 본문으로 작성한다.
6. `ㅇ`은 하나의 평가 논점을 나타내고, `-`는 서로 다른 하위 논거에만 사용한다. 문장마다 `-`를 붙이지 말고 같은 판단의 설명·근거·함의는 2~4문장의 한 문단으로 묶는다.
7. `- 본문`을 기본으로 작성하고, 큰 논거를 구분할 때만 본문과 일치하는 괄호 소제목 하나를 사용한다. 같은 `ㅇ` 아래에서 같은 요약어를 반복하거나 소제목 뒤에 다시 괄호 소제목을 붙이지 않는다. 같은 논거의 문장은 한 문단으로 합친다.

[세부 판단 기준]
- 성평등은 성별 분리통계, 여성 참여, 모자보건 접근성, 성인지적 사업설계, 여성 수혜자 또는 종사자 역량강화 근거를 보고 판단한다.
- 취약계층·인권은 지역, 소득, 장애, 연령, 접근성 제약 등 소외요인을 고려한 대상자 선정과 서비스 접근 개선 근거를 보고 판단한다.
- 환경과 세이프가드는 환경영향, 의료폐기물, 기자재 운영, 시설 개선, 안전관리, 관련 체크리스트와 준수 근거를 보고 판단한다.
- 갈등민감성과 지역사회 수용성은 지역사회 참여, 현지 기관 협의, 민원 또는 갈등 대응, 문화적 수용성 근거를 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 고려했다고 쓰지 말고, 설계, 집행, 모니터링, 성과관리 중 어느 단계에서 어떻게 반영되었는지 설명한다.
- 근거가 제한적인 경우에는 범분야 이슈가 사업성과에 미친 영향과 향후 보완 필요 지점을 의미 단위로 구분하되, 하나의 하위 논거를 문장별 `-`로 잘게 나누지 않는다.

[형식 전용 예시 — 내용은 현재 사업 근거로만 대체]
 ㅇ 젠더·인권·취약계층 고려
  - (포용적 설계) {{CURRENT_SUPPORTED_INCLUSIVE_DESIGN_AND_RESULT}} {{CURRENT_CONNECTED_INTERPRETATION}}
  - (분리통계 한계) {{CURRENT_SUPPORTED_DISAGGREGATED_DATA_LIMITATION}}
  - (이행체계 보완) {{CURRENT_EXECUTABLE_MONITORING_AND_MANAGEMENT_ACTION}}

위 예시의 괄호 요약어는 문단 역할 예시이며, 현재 근거에 맞게 구체화한다. 같은 요약어를 연속 사용하거나 `(후속 과제)` 같은 포괄어로 서로 다른 문단을 반복하지 않는다.

[출력]
범분야 이슈 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
