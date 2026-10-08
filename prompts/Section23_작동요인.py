from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = "[작성 대상]\nVI. 결론 2. 작동요인을 작성한다.\n\n[참고할 입력]\n- prior_analysis_sections: 성과달성도와 기준별 평가결과.\n- reference_corpus: 성공 요인, 협력 구조, 현지 수요, 사업관리 관련 근거.\n- previous_text: 현재 양식과 문체.\n- user_request: 사용자가 직접 입력한 수정 요청.\n\n[작성 규칙]\n1. 작동요인은 사업 성과에 긍정적으로 기여한 설계·수행·협력·환경 요인을 정리한다.\n2. 단순 성과 나열이 아니라 왜 작동했는지를 설명한다.\n3. 앞 섹션의 근거와 충돌하지 않게 작성한다.\n4. 확인되지 않은 성공 요인은 만들지 않는다.\n5. 최종 보고서 본문으로 작성한다.\n\n[출력]\n작동요인 최종 본문만 반환한다."


EDITOR_PROMPT += """

[논점과 소제목 정합성]
- 기본 세부 문단은 `- 본문`이다. 구별이 필요한 큰 논거에만 괄호 소제목 하나를 사용한다.
- 이미 `(현장 적용 효과 검증)` 같은 소제목이 있으면 `(운영 자립)`을 앞에 추가하지 않는다. 괄호 뒤 괄호 구조를 금지한다.
- '운영 자립'은 재원·인력·운영체계의 독립 유지에 관한 판단에만 사용한다. 교육의 현장 적용 효과, 성과 추적·검증 필요성을 운영 자립으로 이름 붙이지 않는다.
- 확인된 작동요인과 아직 검증하지 못한 효과를 구분한다. 후속 검증 필요성을 이미 확인된 성공 요인처럼 서술하지 않는다.

[Few-shot: 형식·논리만 참고, 사례 사실은 현재 사업에 전용 금지]
입력: 관찰된 실행 요인과 향후 효과 확인 필요성이 서로 다른 논거임.
출력:
 ㅇ 실행 요인과 검증 과제
- (실행 여건) 현재 자료에서 확인된 요인과 그 요인이 작동한 경로를 설명함.
- (효과 검증) 관찰 범위를 넘는 효과는 단정하지 않고 추가 확인이 필요한 자료를 설명함.

입력: 이미 'ㅇ 운영체계'에서 논점이 충분히 드러나며 세부 논거는 하나임.
출력:
 ㅇ 운영체계
- 확인된 운영 방식과 그 의미를 연결하여 설명함. 같은 논거의 보완 설명은 이 문단에 이어 작성함.

위 예시 문장 자체를 완성 본문으로 복사하지 말고, 등록 자료로 확인한 사실과 판단만 작성한다.
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
