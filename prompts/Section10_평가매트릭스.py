from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 10: III. 평가개요 - 2. 평가매트릭스(Evaluation Matrix)의 원본 표 셀에 들어갈 값만 작성한다.

[원본 표 구조]
열: 평가기준 | 평가질문 | 측정지표 | 자료출처 | 분석방법
행: 적절성, 일관성, 효과성, 효율성, 지속가능성, 인권/취약계층주류화, 성주류화, 환경주류화
평가기준명과 표 양식은 알고리즘이 보존하므로 출력하지 않는다.

[작성 규칙]
1. 원본 HWPX 표 구조, 제목, 기준명은 수정하지 않는다.
2. 각 slot 값은 해당 표 셀 하나에 들어갈 짧은 문장 또는 구문으로 작성한다.
3. 자료가 부족해도 "추가 정보 필요", "확인 필요", "자료 없음"이라고 쓰지 말고, 제공 자료·사업개요·PDM·평가기준 자료에서 추론 가능한 범위로 작성한다.
4. 평가질문은 질문형 한 문장으로 작성하고, 측정지표·자료출처·분석방법은 쉼표로 구분한 간결한 구문으로 작성한다.
5. 실제 수행하지 않은 조사 방법을 단정하지 말고, 가능한 분석방법은 문헌조사, 이해관계자 면담, 현장확인, 성과자료 검토 등 제공된 자료 기반 범위에서 작성한다.
6. markdown table, XML, 설명문, 본문 문단, 인접 섹션 내용은 절대 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 모든 key를 반드시 포함한다.

{
  "schema": "section10_eval_matrix_slots_v1",
  "slots": {
    "relevance_question": "사업은 수원국 정책과 수요에 적절히 부합하였는가?",
    "relevance_indicator": "정책 부합성, 수요 반영도, 설계 적절성",
    "relevance_source": "사업개요서, 사전조사 자료, 보건정책 자료",
    "relevance_method": "문헌조사, 설계논리 검토, 이해관계자 면담",
    "coherence_question": "타 공여기관 및 정부 사업과 중복 없이 상호보완적으로 연계되었는가?",
    "coherence_indicator": "조정체계, 역할 분담, 연계성",
    "coherence_source": "운영위원회 자료, 공여기관 관련 자료, 면담자료",
    "coherence_method": "문헌조사, 비교분석, 관계자 면담",
    "effectiveness_question": "계획된 산출물과 성과목표가 달성되었는가?",
    "effectiveness_indicator": "산출물 달성도, 성과지표 변화, 수혜자 접근성",
    "effectiveness_source": "PDM, 완료보고서, 성과자료, 종료선 조사 자료",
    "effectiveness_method": "성과자료 검토, 문헌조사, 면담",
    "efficiency_question": "투입 예산과 일정, 운영방식이 효율적으로 관리되었는가?",
    "efficiency_indicator": "예산 집행률, 일정 준수, 투입 대비 산출",
    "efficiency_source": "예산 집행자료, 사업 일정표, 조달·운영 자료",
    "efficiency_method": "투입·산출 비교, 문헌조사, 관계자 면담",
    "sustainability_question": "사업 종료 후 운영·유지관리 체계가 지속될 수 있는가?",
    "sustainability_indicator": "운영체계, 인력 수급, 예산 확보, 제도화 수준",
    "sustainability_source": "사후관리 자료, 운영자료, 기자재 관리대장, 면담자료",
    "sustainability_method": "문헌조사, 운영체계 검토, 면담",
    "human_rights_question": "취약계층의 접근성과 포용성이 사업 설계와 성과관리에서 고려되었는가?",
    "human_rights_indicator": "취약계층 접근성, 서비스 이용 형평성, 참여도",
    "human_rights_source": "사업계획서, 수혜자 자료, 현장·면담자료",
    "human_rights_method": "문헌조사, 수혜자 관점 검토, 면담",
    "gender_question": "여성의 수요와 편익이 사업 설계 및 성과분석에 반영되었는가?",
    "gender_indicator": "여성 수혜 정도, 모성보건 접근성, 성별 성과 차이",
    "gender_source": "성과자료, 보건통계, 수혜자·관계자 면담자료",
    "gender_method": "성별 자료 검토, 문헌조사, 면담",
    "environment_question": "환경 및 시설 운영 위험이 사업 수행과 사후관리에 고려되었는가?",
    "environment_indicator": "환경위험 검토, 의료폐기물 관리, 시설 운영관리",
    "environment_source": "사업계획서, 시설·기자재 자료, 현장확인 자료",
    "environment_method": "문헌조사, 현장확인, 관계자 면담"
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
