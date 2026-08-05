from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
평가등급 결과표에 들어갈 슬롯 값을 작성한다.

[참고할 입력]
- content_inputs.criteria: 기준별 평가점수와 판단 근거.
- grade_score_rows: 시스템이 산정한 기준별 점수 행.
- content_inputs.overall: 종합점수, KOICA 평가등급, 국무조정실 평가등급.
- previous_text: 현재 등급표 또는 이전 JSON 슬롯 값.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 점수는 시스템 입력의 기준별 점수와 종합점수를 그대로 사용한다.
2. 점수 형식은 "3점", 종합점수는 "14/20점" 형식으로 쓴다.
3. 사유는 표 셀에 들어갈 수 있게 한 줄, 90자 이내로 쓴다.
4. 점수는 시스템 입력값을 유지하고, 사유는 content_inputs.criteria의 평가질문별 점수와 핵심 판단을 최우선 근거로 작성한다.
5. 각 기준의 total_reason은 반드시 "{기준명} 종합 평가: ..." 형식으로 쓴다. "종합 평균"이라는 표현은 쓰지 않는다.
6. 효율성은 efficiency_timeliness, efficiency_balance, efficiency_total 세 행을 모두 작성한다. efficiency_total_reason도 반드시 "효율성 종합 평가: ..."로 채운다.
7. 근거 없는 일반론, 사업명만 바꾼 문장, 원본 placeholder 문장, "전반적으로 양호" 같은 추상 표현만 있는 사유는 금지한다.
8. XML, markdown, 설명, 주석은 쓰지 않는다.

[세부 점수 산정 및 산정 이유 작성 기준]
점수는 새로 계산하지 말고 시스템 입력값을 유지하되, 산정 이유는 아래 기준으로 "왜 해당 점수인지"를 설명한다.
- 4점 사유: 3점 조건을 충족하고, 추가 우수요건까지 근거문서와 핵심 판단에서 확인될 때만 그렇게 쓴다.
- 3점 사유: 주요 요건은 충족하지만 참여, 증빙, 품질, 달성범위, 제도화 등 일부 한계가 있을 때 그 한계를 함께 쓴다.
- 2점 사유: 일부 고려 또는 일부 달성은 있으나 분석방식, 조정근거, 실효성, 증빙, 성과연계가 부족한 점을 쓴다.
- 1점 사유: 핵심 요건이 미반영, 미달성, 미대응이거나 성과에 부정적 영향이 확인된 점을 쓴다.
- 각 사유는 "근거문서/핵심 판단 내용 + 점수 기준 충족 또는 미충족 이유" 구조로 작성한다.

평가질문별로 반드시 확인할 근거는 다음과 같다.
- relevance_policy: CPS/CAS, 협력국 정책, 사전·기초조사, PCP/RD, PDM, ToC·문제나무, 수혜자·이해관계자 수요조사에서 정책 부합성, 우선순위, 수요분석 방식, 현지 참여가 확인되는지 본다.
- relevance_adaptation: 정기 모니터링, 사업변경 요청, JSC/운영위원회 회의록, 리스크 대응, 변경 PDM에서 외부 변화 인지, 적기 대응, 실행 가능한 대안, 성과지표 달성 가능성이 확인되는지 본다.
- coherence_internal: KOICA 타 사업, 국내 기관 사업, SDGs·인권·젠더·환경 세이프가드, 국제규범과의 중복·충돌 여부 및 역할분담 근거를 본다.
- coherence_external: 타 공여기관, 수원국 정부, 현지 주체와의 MoU, 조정회의록, RACI, 유사사업 맵에서 중복 회피와 상호보완적 시너지가 입증되는지 본다.
- effectiveness_output: 최신 PDM, 산출물 완료보고서, 활동별 결과보고서, 교육·시설·장비 실적에서 계획 산출물의 수량, 품질, 일정 달성 여부를 본다.
- effectiveness_outcome: 기준선·종료선, 성과지표 실적, 수혜자 조사, 기여도 분석에서 성과목표 달성, 사업 기여, 외부요인 구분 여부를 본다.
- effectiveness_equity: 성별·지역별·취약계층 분리통계, 소외계층 참여 기록, 수혜자 사례에서 형평성과 포용 효과가 확인되는지 본다.
- efficiency_timeliness: 예산 집행, 단가·비용 적정성, 일정표, 조달·계약, 지연 및 시정조치에서 경제성과 시의성이 확인되는지 본다.
- efficiency_balance: 인력·예산 투입, 활동별 투입 기록, 활동 간 조정회의록, 투입 대비 산출 분석에서 투입·활동·산출의 균형과 중복·공백 여부를 본다.
- sustainability_capacity: 운영·유지관리 계획, 예산 확약, 인수인계, 운영 매뉴얼, 현지 인력 교육, 위기대응 계획에서 자립 운영역량과 장기 재원이 확인되는지 본다.
- sustainability_environment: 정책·제도 반영, 공식 승인, 지역사회 참여, 역할분담, 사회적 수용성 근거에서 편익의 장기 제도화 가능성을 본다.
- total_reason: 하위 질문 점수의 평균만 반복하지 말고, 해당 기준에서 점수를 좌우한 핵심 강점과 한계를 함께 쓴다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section4_grade_slots_v1",
  "slots": {
    "project_label": "평가대상 사업명: 사업명(사업기간 / 예산)",
    "relevance_policy_score": "",
    "relevance_policy_reason": "",
    "relevance_adaptation_score": "",
    "relevance_adaptation_reason": "",
    "relevance_total_score": "",
    "relevance_total_reason": "",
    "coherence_internal_score": "",
    "coherence_internal_reason": "",
    "coherence_external_score": "",
    "coherence_external_reason": "",
    "coherence_total_score": "",
    "coherence_total_reason": "",
    "effectiveness_output_score": "",
    "effectiveness_output_reason": "",
    "effectiveness_outcome_score": "",
    "effectiveness_outcome_reason": "",
    "effectiveness_equity_score": "",
    "effectiveness_equity_reason": "",
    "effectiveness_total_score": "",
    "effectiveness_total_reason": "",
    "efficiency_timeliness_score": "",
    "efficiency_timeliness_reason": "",
    "efficiency_balance_score": "",
    "efficiency_balance_reason": "",
    "efficiency_total_score": "",
    "efficiency_total_reason": "",
    "sustainability_capacity_score": "",
    "sustainability_capacity_reason": "",
    "sustainability_environment_score": "",
    "sustainability_environment_reason": "",
    "sustainability_total_score": "",
    "sustainability_total_reason": "",
    "overall_score": "",
    "government_grade": "",
    "koica_grade": "",
    "remove_grade_notice_1": "",
    "remove_grade_notice_2": ""
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
