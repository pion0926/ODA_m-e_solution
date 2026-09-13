from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any


THEORY_VISUAL_DESIGN_VERSION = "six-column-reference-v3-dark-300dpi"
REFERENCE_IMAGE_PATH = Path(
    "/app/samples/report_visual_references/theory_of_change_six_column_reference.png"
)


FACTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "text"],
    "properties": {
        "kind": {"type": "string", "enum": ["working", "nonworking"]},
        "text": {"type": "string"},
    },
}


THEORY_VISUAL_SCHEMA = {
    "name": "oda_theory_of_change_six_column_visual",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "subtitle",
            "challenges",
            "activity_groups",
            "pre_output_factors",
            "outputs",
            "post_output_factors",
            "outcomes",
        ],
        "properties": {
            "title": {"type": "string"},
            "subtitle": {"type": "string"},
            "challenges": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string"},
            },
            "activity_groups": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "items"],
                    "properties": {
                        "label": {"type": "string"},
                        "items": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 3,
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "pre_output_factors": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": FACTOR_SCHEMA,
            },
            "outputs": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string"},
            },
            "post_output_factors": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": FACTOR_SCHEMA,
            },
            "outcomes": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string"},
            },
        },
    },
}


SYSTEM_PROMPT = (
    "당신은 ODA 종료평가 변화이론을 설계하는 수석 평가전문위원이자 정보디자이너다. "
    "첨부 이미지는 시각 문법과 열 구성만 참고하고 그 안의 사업명·내용·사실은 절대 재사용하지 않는다. "
    "제공된 현재 사업 근거에서 확인되는 사실만 사용하며 지정된 JSON 객체만 반환한다."
)


def _reference_data_url(path: Path = REFERENCE_IMAGE_PATH) -> str:
    if not path.is_file():
        # Source checkout and deployed /app have different path depths.
        # Search bounded ancestors rather than indexing a nonexistent parent.
        relative = Path("samples/report_visual_references/theory_of_change_six_column_reference.png")
        path = next(
            (parent / relative for parent in Path(__file__).resolve().parents
             if (parent / relative).is_file()),
            path,
        )
    if not path.is_file():
        raise RuntimeError(f"변화이론 디자인 참고 이미지를 찾을 수 없습니다: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def theory_visual_user_prompt(source: dict[str, Any]) -> str:
    """Editable Claude instructions for the six-column report visual."""

    return f"""첨부 참고 이미지와 동일한 정보 구조의 변화이론 한 장을 설계하라.

[반드시 유지할 시각 구조]
1. 정확히 6개 열을 왼쪽에서 오른쪽으로 배치한다.
   당면과제 → 주요 활동 → 작동·비작동요인 → 산출물 → 작동·비작동요인 → 중장기성과
2. 당면과제·산출물·중장기성과는 각각 독립된 둥근 박스 목록으로 구성한다.
3. 주요 활동은 2~3개 활동 묶음으로 나누고, 각 묶음 안에 2~3개 세부 활동 박스를 둔다.
4. 두 개의 작동·비작동요인 열은 오른쪽 화살표 모양 항목으로 구성한다.
   - working: 성과경로를 촉진한 확인 근거
   - nonworking: 성과경로를 제약하거나 아직 검증되지 않은 조건
5. 같은 사실을 여러 열에 반복하지 말고 원인→활동→산출→성과 인과관계가 읽히도록 배치한다.

[내용 작성 규칙]
- 첨부 이미지의 내용은 예시일 뿐이며 문구·기관·수치·사업 사실을 복사하지 않는다.
- 아래 현재 사업 근거에 없는 수치, 기관, 성과 또는 미래 달성 사실을 만들지 않는다.
- 진행 중이거나 미확인인 결과는 달성으로 단정하지 않는다.
- 각 박스·화살표는 발표용 명사형 문구 16~42자 내외로 압축한다.
- 문서명·페이지 인용, 내부 ID, AI·Claude라는 표현은 넣지 않는다.
- title은 '변화이론 분석'으로 쓰고 subtitle은 현재 사업의 성과경로를 한 문장으로 요약한다.

[현재 사업 근거]
{json.dumps(source, ensure_ascii=False)}
"""


def theory_visual_messages(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a multimodal request so Claude sees the approved reference."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": theory_visual_user_prompt(source)},
                {
                    "type": "image_url",
                    "image_url": {"url": _reference_data_url()},
                },
            ],
        },
    ]
