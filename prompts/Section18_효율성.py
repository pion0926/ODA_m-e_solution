from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 4. 효율성을 작성한다.

[참고할 입력]
- reference_corpus: 예산, 집행, 일정, 조달, 투입 대비 산출, 사업관리 문서.
- content_inputs.criteria: 효율성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 예산 집행, 일정 관리, 조달·시공·운영관리, 투입 대비 산출의 관점에서 분석한다.
2. 점수 라벨이나 표 문구를 그대로 옮기지 않는다.
3. 지연, 비용 증가, 관리상 제약이 있으면 원인과 영향까지 설명한다.
4. 자료가 부족한 경우에도 근거 있는 범위에서 판단하고 한계를 짧게 밝힌다.
5. 최종 보고서 본문으로 작성한다.

[세부 판단 기준]
- 경제성 및 시의성은 예산 집행내역, 집행률 분석표, 예산 변경 승인 문서, 단가 비교 또는 비용 적정성 검토, 사업 일정표, 조달·입찰·계약 문서, 지연 사유와 시정조치 기록을 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 예산이 집행되었다고 쓰지 말고, 예산 편차, 일정 지연, 조달 이슈, 보완조치가 산출물과 성과에 어떤 영향을 주었는지 설명한다.
- 4점 수준의 판단은 예산과 일정이 매우 효율적으로 관리되고 자원 절감, 추가 성과, 지연 최소화, 신속한 시정조치가 확인될 때 작성한다.
- 3점 수준의 판단은 주요 지연 또는 예산 편차가 관리되었으나 일부 조달 지연, 집행 조정, 비용 적정성 근거 부족이 남을 때 작성한다.
- 투입·활동·산출의 균형은 인력 투입 계획, 활동별 투입 기록, 주요 활동 간 조정 회의록, 투입 대비 산출 분석표를 보고 판단한다.
- 투입 균형 판단은 중복 투입, 활동 공백, 특정 산출물 편중, 관리 비효율, 조정체계의 작동 여부를 구분하여 작성한다.

[출력]
효율성 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
