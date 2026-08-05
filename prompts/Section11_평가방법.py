from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
III. 평가개요 3. 평가 방법 본문을 작성한다.

[참고할 입력]
- reference_corpus: 평가계획, 인터뷰 기록, 설문 자료, 현장확인 자료, 문헌 목록.
- content_inputs.criteria: 기준별로 사용한 자료와 분석 방법.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 문헌조사, 정량자료 검토, 이해관계자 면담, 현장확인, 설문 등 제공 자료에서 확인되는 방법을 중심으로 작성한다.
2. 직접 근거가 약한 방법은 단정하지 말고 "자료 검토", "면담자료 확인", "성과자료 대조"처럼 보수적으로 표현한다.
3. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 자료가 제한적이면 가능한 근거를 종합해 방법론 문장으로 완성한다.
4. 각 방법이 평가기준과 평가질문 검토에 어떻게 기여했는지 연결한다.
5. 표, markdown, XML, 코드블록 없이 최종 보고서 본문으로 바로 들어갈 문단/목록만 작성한다.

[세부 생성 기준]
- 문헌조사는 실제로 확인된 자료군을 1차, 2차, 3차 문헌으로 구분해 작성한다.
- 1차 문헌은 KOICA 정책 문서, 협력국 전략, 사업요청서, RD, 사업개요서, PDM, 사업집행계획, 연례보고서, 성과점검 보고서, 종료보고서, 사업변경 승인 내역, 예산계획 대비 집행내역, 성과관리 자료처럼 사업 설계와 집행을 직접 설명하는 자료를 우선한다.
- 2차 문헌은 협력국 국가정책, 부문별 전략, 인구·보건·경제통계, 대상지역 및 수혜인구 배경자료처럼 사업 맥락과 수요를 판단하는 자료를 우선한다.
- 3차 문헌은 국제기구, 타 공여기관, 유사 분야 연구, 경제성 분석, 운영관리 참고자료처럼 비교·해석·제언 도출에 필요한 자료를 우선한다.
- 면담, 설문, 현장확인은 실시 근거가 있는 경우에만 쓰고, 각 방법이 적절성, 일관성, 효과성, 효율성, 지속가능성 판단에 어떤 증거를 제공했는지 연결한다.
- 이전 양식의 placeholder 문장과 동일한 내용을 그대로 반환하지 말고, 현재 reference_corpus와 content_inputs.criteria에 있는 문서명과 분석 목적을 반영한다.

[출력]
평가 방법 최종 텍스트만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
