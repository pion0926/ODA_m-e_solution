from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 7: II. 대상사업개요 - 2. 사업개요 표의 내용 셀만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 표, 행/열, 병합, 글꼴, XML 구조는 절대 수정하지 않는다.
2. 아래 slots의 각 값은 원본 표의 특정 내용 셀 하나를 대체한다.
3. markdown 표, XML, HTML, 코드블록, 설명문을 쓰지 않는다.
4. 각 값은 셀 안에 들어갈 최종 텍스트만 작성한다.
5. 줄바꿈이 필요한 항목은 " / "로 구분한다. <br> 태그를 쓰지 않는다.
6. 자료가 직접 부족해도 사업개요서, reference_corpus, content_inputs.project, prior_analysis_sections를 종합해 최대한 작성한다.
7. 확인되지 않은 인명은 쓰지 말고, 사업명/기간/예산/지역/활동/산출물은 제공 자료 범위에서 보수적으로 작성한다.

[슬롯별 작성 기준]
- project_name_ko: "▣ 국문: ..." 형식.
- project_name_en: "▣ 영문: ..." 형식. 영문명이 없으면 사업명 의미를 자연스럽게 영문 번역한다.
- target_country_region: "▣ 네팔 무구군(Mugu District)"처럼 대상국가와 지역을 함께 쓴다.
- project_period_budget: "▣ 구분 : ... / ▣ 기간 : ... / ▣ 총 사업예산 : ..." 형식.
- project_sector: "▣ 프로젝트 / 보건(모자보건)"처럼 사업유형과 분야를 함께 요약한다.
- project_purpose: 사업 목적을 1~2개 "▣ ..." 항목으로 작성한다.
- pcp_feasibility_review: PCP, 수총기관 공문, 사전타당성조사 관련 핵심 검토사항을 "󰁯 ..." 항목으로 요약한다.
- korean_textbook_development: 우리정부 분담사항 중 교재개발/교육자료 관련 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_equipment_support: 기자재 지원 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_expert_dispatch: 전문가 파견/자문/모니터링 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_invitation_training: 초청연수 또는 현지 교육·훈련 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- partner_contribution: 수원국 또는 파트너 분담사항을 "▣ ..." 형식으로 작성한다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section7_project_overview_slots_v1",
  "slots": {
    "project_name_ko": "▣ 국문: ...",
    "project_name_en": "▣ 영문: ...",
    "target_country_region": "▣ ...",
    "project_period_budget": "▣ 구분 : ... / ▣ 기간 : ... / ▣ 총 사업예산 : ...",
    "project_sector": "▣ ...",
    "project_purpose": "▣ ...",
    "pcp_feasibility_review": "󰁯 관계기관 PCP : ... / 󰁯 수총기관 공문 : ... / 󰁯 사전타당성조사 : ...",
    "korean_textbook_development": "▣ 소요예산 : ... / ▪ ...",
    "korean_equipment_support": "▣ 소요예산 : ... / ▪ ...",
    "korean_expert_dispatch": "▣ 소요예산 : ... / ▪ ...",
    "korean_invitation_training": "▣ 소요예산 : ... / ▪ ...",
    "partner_contribution": "▣ ..."
  }
}
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
