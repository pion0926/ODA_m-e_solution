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
3. 산정 이유는 각 평가질문 행에만 짧은 완결 문장 2개, 120자 이내로 쓴다. 첫 문장은 구체적 성과 또는 미흡사항, 둘째 문장은 해당 사실이 점수에 미친 이유를 설명한다.
4. 점수는 시스템 입력값을 유지하고, 사유는 content_inputs.criteria의 평가질문별 점수와 핵심 판단을 최우선 근거로 작성한다.
5. 평점 소계 행의 five total_reason(relevance/coherence/effectiveness/efficiency/sustainability)은 모두 빈 문자열("")로 반환한다. 평점 행에는 종합 사유를 쓰지 않는다.
6. 효율성은 efficiency_timeliness, efficiency_balance 두 질문 행과 efficiency_total_score 평점 행을 작성하되 efficiency_total_reason은 빈 문자열로 둔다.
7. 근거 없는 일반론, 사업명만 바꾼 문장, 원본 placeholder 문장, "전반적으로 양호" 같은 추상 표현만 있는 사유는 금지한다.
8. XML, markdown, 설명, 주석은 쓰지 않는다.
9. 종합 결과는 시스템의 5개 기준 점수 합계(/20), KOICA 등급(A~F), 국무조정실 등급 문구를 그대로 사용한다. "우수/양호 수준" 같은 비공식 자체 등급을 만들지 않는다.
10. 사유의 첫 문장은 문서에서 확인된 구체적 사실·성과·미흡사항으로 시작한다. "본 사업은", "본 평가는", "핵심 확인사항", "관련 근거가 확인됨" 같은 상투적 머리말·맺음말을 쓰지 않는다.
11. 표 안에서는 문서명·페이지 괄호 인용을 반복하지 않는다. 대신 확인된 사실과 그 사실이 점수에 미친 이유를 한 문장으로 압축한다.
12. 산정 이유에 탭 문자, "\t", 줄바꿈, 들여쓰기 공백, 글머리표를 넣지 않는다. 문장은 셀의 첫 글자부터 시작한다.

[세부 점수 산정 및 산정 이유 작성 기준]
점수는 새로 계산하지 말고 시스템 입력값을 유지하되, 산정 이유는 아래 기준으로 "왜 해당 점수인지"를 설명한다.
- 4점 사유: 3점 조건을 충족하고, 추가 우수요건까지 근거문서와 핵심 판단에서 확인될 때만 그렇게 쓴다.
- 3점 사유: 주요 요건은 충족하지만 참여, 증빙, 품질, 달성범위, 제도화 등 일부 한계가 있을 때 그 한계를 함께 쓴다.
- 2점 사유: 일부 고려 또는 일부 달성은 있으나 분석방식, 조정근거, 실효성, 증빙, 성과연계가 부족한 점을 쓴다.
- 1점 사유: 핵심 요건이 미반영, 미달성, 미대응이거나 성과에 부정적 영향이 확인된 점을 쓴다.
- 각 사유는 "확인된 구체적 사실 + 점수 기준 충족 또는 미충족 이유" 구조로 작성한다.

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
- total_reason: 평가기준별 평점 행에는 산정 이유를 쓰지 않으므로 반드시 빈 문자열로 반환한다.

[Few-shot 형식 예시 — 형식만 참고, 내용 사용 금지]
입력 구조 예시: 질문별 점수와 현재 사업 근거가 주어짐.
출력 구조 예시:
- question_score: 시스템 점수 유지
- question_reason: "현재 사업에서 확인된 사실 + 해당 질문의 점수 기준 충족/미충족 이유."
- total_score: 시스템 산정 평균 유지
- total_reason: ""
이 예시는 행 역할과 빈 셀 규칙만 보여준다. 예시의 사실·수치·판단을 현재 사업 내용으로 사용하지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section4_grade_slots_v1",
  "slots": {
    "project_label": "평가대상 사업명: 사업명",
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
