from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
평가보고서 관련 공지 상자에 들어갈 독자용 본문 문단을 작성한다.

[참고할 입력]
- previous_text: 현재 저장된 공지 본문.
- content_inputs.project: 사업명, 기간, 예산 등 사업 기본 정보.
- reference_corpus: 평가책임자, 수행기관, 품질관리 관련 근거가 있을 때만 사용한다.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 자료 기반 판단의 범위, 자료 한계, 최종 사실확인과 품질검토, 개인정보와 출처 인용 원칙을 문단으로 쓴다.
2. 근거가 없는 외부 심의·현지조사·면담 수행 사실이나 평가등급을 만들지 않는다.
3. 평가자·국가명·평가일·심의위원 등 메타데이터 칸은 양식이 처리하므로 슬롯 이름이나 값을 본문에 나열하지 않는다.
4. schema, slots, placeholder, XML, markdown 코드블록을 쓰지 않는다.
5. 사용자의 수정 요청을 반영하되 확인되지 않은 내용을 완료 사실로 쓰지 않는다.

[출력 형식]
공지 본문만 반환한다. 보고서 생성 API가 JSON 응답을 요구하면 content 문자열 안에 본문을 담는다.
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
