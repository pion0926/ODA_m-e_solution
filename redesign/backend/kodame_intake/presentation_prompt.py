from __future__ import annotations

import json
from typing import Any

from .presentation_reference import prompt_reference_payload


SLIDE_COUNT = 12
ROLE_SEQUENCE = (
    "cover",
    "executive_summary",
    "context",
    "project_profile",
    "pdm",
    "methodology",
    "achievement",
    "assessment",
    "crosscutting",
    "factors_lessons",
    "recommendations",
    "closing",
)
LAYOUT_SEQUENCE = (
    "cover",
    "statement",
    "split",
    "snapshot",
    "pdm_flow",
    "timeline",
    "metric_grid",
    "score_bars",
    "evidence",
    "comparison",
    "roadmap",
    "closing",
)
ALLOWED_LAYOUTS = frozenset(LAYOUT_SEQUENCE)
ROLE_SOURCE_FALLBACKS = {
    "cover": ("cover",),
    "executive_summary": ("summary-ko", "grade", "conclusion"),
    "context": ("project-background",),
    "project_profile": ("project-overview",),
    "pdm": ("pdm",),
    "methodology": ("eval-purpose", "eval-matrix", "eval-methods", "eval-limitations"),
    "achievement": ("achievement",),
    "assessment": (
        "criteria-relevance", "criteria-coherence", "criteria-effectiveness",
        "criteria-efficiency", "criteria-sustainability",
    ),
    "crosscutting": ("criteria-crosscutting", "criteria-other"),
    "factors_lessons": ("working-factors", "nonworking-factors", "theory", "lessons"),
    "recommendations": ("feedback",),
    "closing": ("conclusion", "feedback"),
}

# The renderer uses different content zones by role.  These limits are kept
# next to the prompt so model instructions and deterministic normalization do
# not drift apart.
ROLE_TEXT_BUDGETS = {
    "cover": {"title": 22, "bullets": 0, "bullet_chars": 0},
    "executive_summary": {"title": 30, "bullets": 3, "bullet_chars": 52},
    "context": {"title": 32, "bullets": 3, "bullet_chars": 58},
    "project_profile": {"title": 32, "bullets": 3, "bullet_chars": 58},
    "pdm": {"title": 32, "bullets": 3, "bullet_chars": 58},
    "methodology": {"title": 32, "bullets": 4, "bullet_chars": 62},
    "achievement": {"title": 32, "bullets": 3, "bullet_chars": 62},
    "assessment": {"title": 32, "bullets": 3, "bullet_chars": 50},
    "crosscutting": {"title": 32, "bullets": 3, "bullet_chars": 58},
    "factors_lessons": {"title": 32, "bullets": 3, "bullet_chars": 58},
    "recommendations": {"title": 32, "bullets": 4, "bullet_chars": 70},
    "closing": {"title": 32, "bullets": 3, "bullet_chars": 58},
}


PLAN_SCHEMA = {
    "name": "oda_evaluation_executive_presentation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["deck_title", "subtitle", "design", "slides"],
        "properties": {
            "deck_title": {"type": "string"},
            "subtitle": {"type": "string"},
            "design": {
                "type": "object",
                "additionalProperties": False,
                "required": ["palette", "mood", "design_rationale"],
                "properties": {
                    "palette": {"type": "string", "enum": ["ocean", "forest", "ink", "cobalt"]},
                    "mood": {"type": "string"},
                    "design_rationale": {"type": "string"},
                },
            },
            "slides": {
                "type": "array",
                "minItems": SLIDE_COUNT,
                "maxItems": SLIDE_COUNT,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "slide_number", "role", "layout", "eyebrow", "title", "headline",
                        "body", "bullets", "secondary_bullets", "metrics", "metric_value",
                        "metric_label", "quote", "steps", "accent", "visual_direction",
                        "speaker_notes", "source_sections", "source_documents",
                    ],
                    "properties": {
                        "slide_number": {"type": "integer"},
                        "role": {"type": "string", "enum": list(ROLE_SEQUENCE)},
                        "layout": {"type": "string", "enum": list(ALLOWED_LAYOUTS)},
                        "eyebrow": {"type": "string"},
                        "title": {"type": "string"},
                        "headline": {"type": "string"},
                        "body": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                        "secondary_bullets": {"type": "array", "items": {"type": "string"}},
                        "metrics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["value", "label", "context"],
                                "properties": {
                                    "value": {"type": "string"},
                                    "label": {"type": "string"},
                                    "context": {"type": "string"},
                                },
                            },
                        },
                        "metric_value": {"type": "string"},
                        "metric_label": {"type": "string"},
                        "quote": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "accent": {"type": "string", "enum": ["blue", "teal", "orange"]},
                        "visual_direction": {"type": "string"},
                        "speaker_notes": {"type": "string"},
                        "source_sections": {"type": "array", "items": {"type": "string"}},
                        "source_documents": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    },
}


SYSTEM_PROMPT = """당신은 ODA 종료평가 전문위원이자 국제개발협력 분야의 수석 프레젠테이션 에디터다.
발주기관·수행기관·평가위원이 의사결정을 내릴 수 있는 고위급 브리핑을 설계한다.

<non_negotiable>
- 제공된 27개 보고서 저장 초안과 근거자료에 명시된 사실만 사용한다.
- 보고서 저장 초안은 HWPX 조판 전 원문이며 발표 내용의 최우선 단일 원본이다.
- 수치, 사업성과, 조사 수행 여부, 인용, 기관명 또는 등급을 추정하거나 새로 만들지 않는다.
- 근거가 불충분하면 과장하지 말고 '추가 확인 필요'라는 판단과 그 이유를 간결하게 쓴다.
- 화면에 보이는 문장은 청중용으로 작성하며 제작 지시, 프롬프트, AI·Claude 언급을 노출하지 않는다.
- 예시 발표자료는 양식, 정보 위계, 전개 방식만 참고한다. 예시의 국가·기관·사업명·수치·문장·결론은 절대 사용하지 않는다.
- 예시의 좌표나 장식을 복제하지 않고, 지정된 디자인 변형 안에서 새로운 구도를 설계한다.
- 제목은 항목명이 아니라 발표자가 말할 수 있는 판단문으로 작성한다.
- 정확히 지정된 JSON 스키마 하나만 반환하고 Markdown 코드블록을 사용하지 않는다.
</non_negotiable>

<editorial_standard>
- 한 장에는 하나의 주장만 둔다.
- 장식보다 정보 위계, 근거, 의미, 의사결정 연결을 우선한다.
- 사실 → 의미 → 시사점 또는 조치가 한 흐름으로 읽혀야 한다.
- 문장을 짧게 쓰고 보고서 문단을 그대로 복사하지 않는다.
- 표보다 메시지, 비교, 흐름, 수치, 로드맵에 적합한 시각 구조를 선택한다.
</editorial_standard>"""


FEW_SHOT = {
    "input_pattern": {
        "claim": "사업의 핵심 산출물은 확인되었으나 장기성과 자료는 아직 제한적임",
        "evidence": ["제도 승인 자료", "교육과정 운영자료", "장기 추적자료 미확보"],
    },
    "good_slide_pattern": {
        "title": "핵심 산출물은 확인됐지만 성과의 지속 여부는 후속 추적이 필요함",
        "headline": "확인된 진척과 아직 검증되지 않은 성과를 분리해 판단함",
        "bullets": [
            "제도·교육 기반 구축은 문서로 확인됨",
            "장기 고용·현장 성과는 추적자료가 부족함",
            "후속 측정 시점과 책임주체를 확정해야 함",
        ],
        "why_good": "사실, 제한, 의사결정 과제를 한 장의 주장으로 연결함",
    },
    "avoid": {
        "title": "성과달성도",
        "bullets": ["보고서 전체 문단 복사", "근거 없는 성공 표현", "한 장에 8개 이상 항목"],
        "why_bad": "주장이 없고 과밀하며 의사결정 의미가 드러나지 않음",
    },
}


def presentation_prompt(
    source: dict[str, Any],
    reference_context: dict[str, Any] | None = None,
    qa_feedback: list[str] | None = None,
) -> str:
    reference_payload = prompt_reference_payload(reference_context or {})
    feedback = qa_feedback or []
    return f"""<communication_job>
발표가 끝날 때 평가 의사결정자는 사업의 필요성·설계·성과·DAC 판단·제약을 이해하고,
어떤 후속조치를 누가 언제 어떤 근거로 확인해야 하는지 결정할 수 있어야 한다.
</communication_job>

<narrative_arc>
1. 표지: 제목과 사업 식별정보만 간결하게 제시
2. 종합판단: 전체 발표의 결론과 가장 중요한 의사결정
3. 문제와 필요성: 대상지역의 문제, 사업 필요성, 개입 논리
4. 사업 한눈에 보기: 기간·예산·대상·핵심 활동·수혜자
5. PDM 성과경로: 투입/활동 → 산출물 → 성과 → 영향, 가정·위험
6. 평가 설계: 목적·범위·방법·근거·한계를 투명하게 설명
7. 성과달성도: 핵심 지표와 확인된 성과, 미확인 성과를 구분
8. DAC 평가결과: 5개 기준 점수와 점수의 의미, 강점·보완점
9. 범분야 이슈: 젠더·인권·취약계층·환경 등 확인 결과와 근거 공백
10. 작동·비작동요인과 교훈: 무엇이 성과를 촉진·제약했는지 설명
11. 우선순위 권고: 책임주체·시점·확인지표가 있는 실행 로드맵
12. 결론: 의사결정자가 기억하고 승인해야 할 최종 메시지
</narrative_arc>

<layout_and_fit_contract>
- layout은 1~12장 순서에 맞춰 {', '.join(LAYOUT_SEQUENCE)}를 사용한다.
- 인접 장은 같은 실루엣을 쓰지 않고 전체에서 최소 9개 이상의 레이아웃을 사용한다.
- 제목은 공백 포함 34자 이내의 한 줄 판단문으로 쓴다.
- headline은 75자, body는 220자 이내로 제한한다.
- bullets와 secondary_bullets는 각각 최대 4개, 항목당 85자 이내로 제한한다.
- 2장 종합판단의 bullets는 최대 3개, 항목당 52자 이내로 제한한다.
- 8장 DAC 평가결과의 bullets는 최대 3개, 항목당 50자 이내로 제한한다.
- 9장 범분야 이슈와 10장 작동·비작동요인의 각 목록은 최대 3개, 항목당 58자 이내로 제한한다.
- steps는 최대 5개, metrics는 최대 4개이며 숫자는 입력 자료에 존재할 때만 사용한다.
- 11장 roadmap의 steps는 반드시 `과제명 | 책임주체 | 완료시점 또는 점검주기 | 확인자료` 순서로 작성한다.
- roadmap 과제명은 24자, 책임주체는 24자, 시점은 18자, 확인자료는 30자 이내로 압축한다.
- 5장 pdm_flow의 steps는 정확히 4개이며 `투입·활동:`, `산출물:`, `성과:`, `영향:` 순서와 접두어를 지킨다.
- 50pt 표지, 35pt 슬라이드 제목, 24pt 중간 제목, 16pt 본문이 가능한 분량만 작성한다.
- 한 장에 내용이 넘칠 것 같으면 글씨를 줄이지 말고 문장을 압축한다.
- visual_direction은 여백, 강조점, 시선 흐름을 설명하되 화면 문구로 노출되지 않는다.
- speaker_notes에는 발표자가 설명할 핵심 맥락을 3~6문장으로 쓰고 새 사실을 추가하지 않는다.
</layout_and_fit_contract>

<reference_deck_contract mode="format_and_flow_only">
- source_folder_url은 샘플의 출처 식별용이다. 링크 내용을 읽었다고 가정하거나 샘플의 사실을 생성하지 않는다.
- content_firewall.allowed 항목만 참고하고 content_firewall.forbidden 항목은 생성 결과에 포함하지 않는다.
- narrative_patterns와 visual_patterns를 현재 사업의 사실에 맞게 재구성한다.
- selected_variant는 이번 생성에서 사용할 통제된 디자인 변형이다. 팔레트는 selected_variant.palette와 일치시킨다.
- 같은 변형 안에서는 글꼴, 여백, 정렬 기준을 고정하고, 장표마다 실루엣만 목적에 맞게 바꾼다.
- 샘플과 동일한 슬라이드를 만들지 말고 색상 면, 축선, 강조 위치 중 최소 두 요소를 새롭게 조합한다.
{json.dumps(reference_payload, ensure_ascii=False, indent=2)}
</reference_deck_contract>

<previous_qa_feedback>
{json.dumps(feedback, ensure_ascii=False, indent=2)}
</previous_qa_feedback>

<source_contract>
- report_sections.content는 HWPX 조판 전 원문이며 발표 내용의 최우선 단일 원본이다.
- source_sections에는 반드시 아래 report_sections의 part_id만 기록한다.
- source_documents에는 반드시 evidence_catalog의 file_name만 기록한다.
- 모든 비자명한 판단과 수치는 source_sections 또는 source_documents로 추적 가능해야 한다.
- 원문 파일명과 페이지 인용은 슬라이드 본문에 반복하지 말고 발표자 노트의 [Sources] 아래에 남긴다.
</source_contract>

<few_shot_format_only>
다음 예시는 내용이 아니라 주장 구성 방식만 참고한다.
{json.dumps(FEW_SHOT, ensure_ascii=False, indent=2)}
</few_shot_format_only>

<project_summary>
{json.dumps(source['summary'], ensure_ascii=False, indent=2)}
</project_summary>

<report_sections source_of_truth="report_sections.content_before_hwpx">
{json.dumps(source['report_sections'], ensure_ascii=False, indent=2)}
</report_sections>

<pdm_and_evaluation_data>
{json.dumps(source['structured_evidence'], ensure_ascii=False, indent=2)}
</pdm_and_evaluation_data>

<evidence_catalog>
{json.dumps(source['evidence_catalog'], ensure_ascii=False, indent=2)}
</evidence_catalog>

이 자료만 사용하여 정확히 {SLIDE_COUNT}장의 발표 설계 JSON을 작성하라.
"""
