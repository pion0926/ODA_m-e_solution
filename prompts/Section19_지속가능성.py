from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
V. 기준별 평가결과 5. 지속가능성을 작성한다.

[참고할 입력]
- reference_corpus: 운영·유지관리, 예산 확보, 인력 역량, 제도화, 현지 주인의식 관련 자료.
- content_inputs.criteria: 지속가능성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 제도적, 재정적, 조직·인력, 시설·기자재 유지관리, 지역사회 수용성 관점으로 분석한다.
2. 지속가능성이 높은 요소와 취약 요소를 구분해 쓴다.
3. 점수 라벨이나 질문 반복은 쓰지 않는다.
4. 후속 운영 가능성은 근거가 있는 범위에서만 판단한다.
5. 최종 보고서 본문만 반환한다.

[세부 판단 기준]
- 운영역량·재정·위기대응은 운영·유지관리 계획, 지방정부 또는 파트너 기관 예산 확약서, 인수인계 문서, 운영 매뉴얼, 현지 인력 역량강화 계획 및 교육 결과, 리스크·위기대응 계획을 보고 판단한다.
- 높은 평가를 받은 경우에는 운영계획 존재만 쓰지 말고, 운영 주체, 예산 출처, 책임체계, 인력 역량, 위기대응 절차가 실제로 지속 가능한지 설명한다.
- 4점 수준의 판단은 현지 시스템과 조직이 자립 운영역량, 장기 재원, 책임체계, 위기대응능력을 명확히 확보한 경우에 작성한다.
- 3점 수준의 판단은 운영체계와 담당 조직 역량은 마련되었으나 예산 확약, 인수인계 완결성, 장기 운영재원, 위기대응 근거가 일부 제한될 때 작성한다.
- 제도적·사회적 환경은 정책·제도 반영 또는 공식 승인 문서, 지역사회 참여 및 수용성 확인 자료, 운영 담당 조직의 역할분담 문서, 장기 재원조달 또는 수익모델 자료를 보고 판단한다.
- 제도화 가능성은 정책 반영, 현지 정부의 소유권, 지역사회 수용성, 사업 편익 확산 가능성을 구분하여 작성한다.

[출력]
지속가능성 평가결과 최종 본문만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
