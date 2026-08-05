from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
III. 평가개요 5. 평가팀 구성 및 시행체계 본문을 작성한다.

[참고할 입력]
- reference_corpus: 평가자 명단, 역할분담표, 수행기관 정보, 품질관리 체계.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 평가책임자, 평가자, 품질관리, 수행기관, 역할분담을 제공 자료에 근거해 정리한다.
2. 개인명·소속·직책 근거가 없으면 이름을 만들지 말고, 평가책임자/분야전문가/평가보조원 등 역할 중심으로 작성한다.
3. "추가 정보 필요", "자료 없음", "확인 필요", "확인 중" 같은 안내문을 쓰지 않는다.
4. 수행체계는 KOICA, 수행기관, 현지 이해관계자, 품질검토 절차의 관계가 보이도록 작성한다.
5. 개인정보나 연락처는 쓰지 않는다. 표, markdown, XML, 코드블록 없이 최종 본문만 작성한다.

[출력]
평가팀 구성 및 시행체계 최종 텍스트만 반환한다."""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
