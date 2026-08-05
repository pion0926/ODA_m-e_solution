from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 3. 효과성을 작성한다.

[참고할 입력]
- reference_corpus: PDM, 성과지표 실적, 산출물 점검, 인터뷰, 설문, 종료보고서 등 효과성 판단 근거.
- content_inputs.criteria: 효과성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 샘플 보고서처럼 산출물 달성, 성과 달성, 목표 달성 가능성, 수혜자 변화 등을 항목별로 분석한다.
2. '평가점수 2/4' 같은 라벨이나 표 내용을 그대로 복사하지 않는다.
3. 실적 수치가 있으면 목표 대비 의미를 설명하고, 수치가 없으면 확인 가능한 정성 근거를 중심으로 쓴다.
4. 긍정적 변화와 미달 요인을 모두 포함해 왜 해당 평가가 나왔는지 드러나게 한다.
5. 최종 보고서 문단으로 작성하고, 설명이나 파일 경로는 쓰지 않는다.

[세부 판단 기준]
- 산출물 달성은 최신 PDM, 산출물 완료보고서, 활동별 결과보고서, 교육·시설·장비 제공 실적, 현장점검 기록을 보고 판단한다.
- 산출물 평가는 수량 달성만 보지 말고 품질, 범위, 일정, 사용 가능성, 산출물이 성과로 연결된 근거를 함께 설명한다.
- 성과 및 목표 달성은 기준선·종료선 조사, 성과지표 실적표, 수혜자 만족도, 성과 기여도 분석, 외부요인 검토 자료를 보고 판단한다.
- 4점 수준의 판단은 목표 성과가 모두 달성되고 사업 개입에 따른 명확한 변화 또는 추가 긍정 성과가 확인될 때 작성한다.
- 3점 수준의 판단은 주요 산출물과 성과가 대체로 달성되었으나 일부 지표, 품질, 기여도 구분, 외부요인 통제에 한계가 있을 때 작성한다.
- 형평성은 성별·지역별·취약계층 분리통계, 소외계층 참여자 명단, 지원 실적, 수혜자 인터뷰 또는 사례 기록을 보고 판단한다.
- 취약계층 포용은 단순 언급이 아니라 설계, 집행, 성과관리 단계에서 실제로 어떻게 반영되었는지 써야 한다.

[출력]
효과성 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
