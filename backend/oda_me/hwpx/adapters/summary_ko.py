from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .contracts import AdapterContract, AdapterContractError, SlotContract


SUMMARY_KO_SCHEMA = "section5_summary_document_v2"
SUMMARY_KO_PATH = "Contents/section3.xml"


@dataclass(frozen=True)
class SummaryBlock:
    key: str
    heading: str
    paragraph_index: int
    min_chars: int
    max_chars: int
    min_detail_paragraphs: int
    required_labels: tuple[str, ...]


SUMMARY_KO_BLOCKS = (
    SummaryBlock("project_overview", "(1) 대상사업개요", 2, 800, 1800, 6, ("사업 기본정보", "추진배경 및 주요내용")),
    SummaryBlock("evaluation_overview", "(2) 평가개요", 11, 800, 1900, 6, ("평가 목적과 범위", "평가 방법", "평가의 한계")),
    SummaryBlock("achievement", "(3) 성과달성도", 23, 800, 1900, 6, ("주요 성과달성도",)),
    SummaryBlock(
        "criteria_results",
        "(4) 기준별 평가결과",
        26,
        1400,
        3600,
        10,
        ("적절성", "일관성", "효과성", "효율성", "지속가능성"),
    ),
    SummaryBlock(
        "conclusion",
        "(5) 결론",
        46,
        1000,
        2700,
        8,
        ("종합 결론", "작동요인", "비작동요인", "환류과제 및 교훈"),
    ),
)
SUMMARY_KO_BLOCK_BY_KEY = {item.key: item for item in SUMMARY_KO_BLOCKS}
SUMMARY_KO_SECTION_HEADINGS = tuple(item.heading for item in SUMMARY_KO_BLOCKS)

# Parenthetical labels are reserved for the two genuinely index-like summary
# groups.  Other ㅇ groups read more naturally as plain report bullets and are
# deliberately normalized to ``- 본문``.  Keeping this policy beside the
# section adapter makes it independently editable without changing the shared
# narrative-section formatter.
SUMMARY_KO_LABELLED_PARENT_TOPICS = frozenset({"사업 기본정보", "주요 성과달성도"})


def _slot(block: SummaryBlock) -> SlotContract:
    return SlotContract(
        key=block.key,
        paragraph_index=block.paragraph_index,
        outline_kind="subheading",
        para_pr_id=67,
        char_pr_id=18,
        source_parts=("summary-ko",),
        max_chars=block.max_chars,
        authoring_prefix="",
        rendered_prefix="",
        min_body_chars=block.min_chars,
    )


SUMMARY_KO_ADAPTER = AdapterContract(
    adapter_id="summary_5_blocks_v3",
    part_id="summary-ko",
    schema=SUMMARY_KO_SCHEMA,
    section_number=5,
    hwpx_path=SUMMARY_KO_PATH,
    slots=tuple(_slot(block) for block in SUMMARY_KO_BLOCKS),
)
SUMMARY_KO_ADAPTER.validate_definition()
SUMMARY_KO_SLOT_KEYS = SUMMARY_KO_ADAPTER.slot_keys


_INLINE_PAGE_CITATION = re.compile(
    r"\s*\([^()\n]{0,220}(?:pp?\.\s*\d+(?:\s*[-–~]\s*\d+)?|\d+\s*쪽)[^()\n]{0,120}\)",
    re.IGNORECASE,
)
_FORBIDDEN_PLACEHOLDERS = (
    "추가 정보 필요",
    "확인 필요",
    "확인 중",
    "미기재",
    "자동 초안 생성 제약",
    "작성 예시",
    "샘플 입력",
    "{{CURRENT_",
)


def _clean_line(value: object) -> str:
    text = str(value or "").replace("\t", " ")
    text = re.sub(
        r"\*\*(.*?)\*\*|__(.*?)__|`([^`]*)`",
        lambda match: next((group for group in match.groups() if group is not None), ""),
        text,
    )
    text = re.sub(r"^\s*#{1,6}\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_summary_ko_page_citations(value: object) -> str:
    """Remove reader-disrupting document/page parentheses without changing claims."""
    text = _INLINE_PAGE_CITATION.sub("", str(value or ""))
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"(?m)[ \t]+$", "", text)
    return re.sub(r" {2,}", " ", text).strip()


def normalize_summary_ko_value(value_key: str, value: object) -> str:
    """Canonicalize one summary block without changing its reader-facing meaning."""
    if value_key not in SUMMARY_KO_BLOCK_BY_KEY:
        raise AdapterContractError(f"summary-ko: 알 수 없는 블록 키 {value_key}")
    lines: list[str] = []
    parent_label = ""
    for raw in str(value or "").replace("\r", "").split("\n"):
        line = _clean_line(raw)
        if not line:
            continue
        if re.match(r"^(?:ㅇ|○|◦|❍|∙|ㆍ)\s*", line):
            body = re.sub(r"^(?:ㅇ|○|◦|❍|∙|ㆍ)\s*", "", line).strip()
            lines.append(f" ㅇ {body}")
            parent_label = body
        elif re.match(r"^(?:-|–|—|•)\s*", line):
            body = re.sub(r"^(?:-|–|—|•)\s*", "", line).strip()
            # A parenthetical keyword is an optional navigation aid in the
            # Korean summary, not a mandatory prefix for every sentence.  Keep
            # labels only in the two configured index-like groups and never
            # manufacture one during parsing/export.  Manual save and HWPX
            # export share this normalizer, preserving draft/document identity.
            if parent_label not in SUMMARY_KO_LABELLED_PARENT_TOPICS:
                body = re.sub(r"^\([^()]{2,15}\)\s+", "", body).strip()
            # The HWPX detail paragraph style owns the visual indentation.
            # Keeping literal spaces before '-' would apply the indent twice.
            lines.append(f"- {body}")
        else:
            lines.append(line)
    return "\n".join(lines)


def summary_ko_body(value_key: str, value: object) -> str:
    return normalize_summary_ko_value(value_key, value)


@dataclass(frozen=True)
class SummaryPayloadValidation:
    ok: bool
    errors: tuple[str, ...]
    normalized_slots: dict[str, str]


def validate_summary_ko_payload(slots: object) -> SummaryPayloadValidation:
    errors: list[str] = []
    if not isinstance(slots, dict):
        return SummaryPayloadValidation(False, ("summary-ko 블록 payload가 객체가 아닙니다.",), {})
    expected = set(SUMMARY_KO_SLOT_KEYS)
    actual = {str(key) for key in slots}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append("누락 블록: " + ", ".join(missing))
    if extra:
        errors.append("알 수 없는 블록: " + ", ".join(extra))

    normalized: dict[str, str] = {}
    for block in SUMMARY_KO_BLOCKS:
        raw = str(slots.get(block.key, "") or "")
        value = normalize_summary_ko_value(block.key, raw)
        normalized[block.key] = value
        lines = [line for line in value.splitlines() if line.strip()]
        if not lines:
            errors.append(f"{block.key}: 본문이 비었습니다.")
            continue
        invalid_lines = [line for line in lines if not re.match(r"^\s*(?:ㅇ|-)\s+\S", line)]
        if invalid_lines:
            errors.append(f"{block.key}: 모든 문단은 ㅇ 또는 - 계층으로 시작해야 합니다.")
        declarative_details = [
            line for line in lines
            if line.lstrip().startswith("- ")
            and re.search(r"(?:다|습니다)\.", line)
        ]
        if declarative_details:
            endings = re.findall(r"[가-힣]+(?:다|습니다)\.", " ".join(declarative_details))[:3]
            errors.append(f"{block.key}: - 문단은 ~함·~음·~됨의 개조식 종결이어야 합니다. 잔여 종결형: {', '.join(endings)}")
        labels_for_parent: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("ㅇ "):
                labels_for_parent = set()
                continue
            detail = re.match(r"^-\s+\(([^()]{2,15})\)\s+", stripped)
            if not detail:
                continue
            label = detail.group(1).strip()
            if label in labels_for_parent:
                errors.append(f"{block.key}: 같은 ㅇ 문단에서 요약어 '{label}'이 중복되었습니다.")
            labels_for_parent.add(label)
        if lines and not lines[0].lstrip().startswith("ㅇ "):
            errors.append(f"{block.key}: 첫 문단은 ㅇ 상위 항목이어야 합니다.")
        for label in block.required_labels:
            if not any(label in line for line in lines if line.lstrip().startswith("ㅇ ")):
                errors.append(f"{block.key}: 필수 하위 항목 '{label}'이 없습니다.")
        detail_count = sum(1 for line in lines if line.lstrip().startswith("- "))
        if len(value) < block.min_chars:
            errors.append(f"{block.key}: 4쪽 이상 요약을 위한 최소 {block.min_chars}자에 미달했습니다.")
        if detail_count < block.min_detail_paragraphs:
            errors.append(
                f"{block.key}: 세부 - 문단이 {detail_count}개이며 최소 {block.min_detail_paragraphs}개가 필요합니다."
            )
        if len(value) > block.max_chars:
            errors.append(f"{block.key}: {block.max_chars}자 블록 용량을 초과했습니다.")
        if any(token in value for token in _FORBIDDEN_PLACEHOLDERS):
            errors.append(f"{block.key}: 독자용 문서에 허용되지 않는 placeholder가 있습니다.")
        if _INLINE_PAGE_CITATION.search(raw):
            errors.append(f"{block.key}: 국문 요약에 문서명·페이지 괄호 인용이 남아 있습니다.")
        if re.search(r"(?:\*\*|__|`|^\s*#{1,6}\s+|\|)", raw, re.MULTILINE):
            errors.append(f"{block.key}: Markdown 표기가 남아 있습니다.")
    return SummaryPayloadValidation(not errors, tuple(errors), normalized)


def assert_summary_ko_payload(slots: object) -> dict[str, str]:
    validation = validate_summary_ko_payload(slots)
    if not validation.ok:
        raise AdapterContractError("국문 요약 5블록 계약 실패: " + "; ".join(validation.errors))
    return validation.normalized_slots


def _render_normalized_summary_ko_document(normalized: dict[str, str]) -> str:
    def spaced_body(value: str) -> str:
        rendered: list[str] = []
        for line in value.splitlines():
            if line.strip().startswith("ㅇ ") and rendered and rendered[-1] != "":
                rendered.append("")
            rendered.append(line)
        return "\n".join(rendered)

    # One empty line separates every hierarchy transition: (n) -> ㅇ and one
    # ㅇ group -> the next ㅇ group.  HWPX uses the same rendered document, so
    # the editor draft and final document keep an identical paragraph rhythm.
    return "\n\n".join(
        f"{block.heading}\n\n{spaced_body(normalized[block.key])}"
        for block in SUMMARY_KO_BLOCKS
    )


def render_summary_ko_document(slots: object) -> str:
    return _render_normalized_summary_ko_document(assert_summary_ko_payload(slots))


def normalize_summary_ko_document(value: object) -> str:
    """Normalize an editable five-heading draft without enforcing page length.

    Manual editor saves stay permissive while sharing the exact marker,
    optional parenthetical summary-label and nominal-ending rules used by
    generation and HWPX export.
    """

    slots = _parse_plain_document(str(value or "").strip())
    normalized = {
        block.key: normalize_summary_ko_value(block.key, slots[block.key])
        for block in SUMMARY_KO_BLOCKS
    }
    return _render_normalized_summary_ko_document(normalized)


def _body_without_prefix(value: object) -> str:
    text = _clean_line(value)
    text = re.sub(r"^(?:가[.)]\s*사업명\s*[:：]?|ㅇ|-)\s*", "", text).strip()
    text = re.sub(r"^\((?:사업개요|평가목적|평가범위)\)\s*", "", text).strip()
    return text


def _migrate_v1_slots(slots: dict) -> dict[str, str]:
    """Group the former 27 paragraph slots into the five reader-facing blocks."""
    def body(key: str) -> str:
        return _body_without_prefix(slots.get(key, ""))

    project_name = body("project_name_line")
    return {
        "project_overview": "\n".join((
            " ㅇ 사업 기본정보",
            f"- 사업명: {project_name}",
            " ㅇ 추진배경 및 주요내용",
            f"- {body('business_background')} {body('business_overview')}".strip(),
        )),
        "evaluation_overview": "\n".join((
            " ㅇ 평가 목적과 범위",
            f"- {body('evaluation_purpose')} {body('evaluation_scope')}".strip(),
            " ㅇ 평가 방법",
            f"- {body('evaluation_method_overview')} {body('document_review_method')} {body('stakeholder_interview_method')} {body('field_survey_method')}".strip(),
            " ㅇ 평가의 한계",
            f"- {body('evaluation_limitations')}",
        )),
        "achievement": "\n".join((
            " ㅇ 주요 성과달성도",
            f"- {body('achievement_summary')}",
        )),
        "criteria_results": "\n".join(
            line
            for key, label in (
                ("relevance_summary", "적절성"),
                ("coherence_summary", "일관성"),
                ("effectiveness_summary", "효과성"),
                ("efficiency_summary", "효율성"),
                ("sustainability_summary", "지속가능성"),
            )
            for line in (f" ㅇ {label}", f"- {body(key)}")
        ),
        "conclusion": "\n".join((
            " ㅇ 종합 결론",
            f"- {body('conclusion_goal_achievement')} {body('conclusion_dac_results')} {body('conclusion_crosscutting_results')}".strip(),
            " ㅇ 작동요인",
            f"- {body('lesson_working_factors')}",
            " ㅇ 비작동요인",
            f"- {body('lesson_nonworking_factors')}",
            " ㅇ 환류과제 및 교훈",
            f"- {body('recommendation_project_model')} {body('recommendation_project_management')} {body('recommendation_structural_limits')} {body('recommendation_other')}".strip(),
        )),
    }


def _parse_plain_document(value: str) -> dict[str, str]:
    text = str(value or "").replace("\r", "").strip()
    matches = list(re.finditer(
        r"(?m)^\s*(?:\(([1-5])\)|([1-5])\.)\s*(대상사업\s*개요|평가\s*개요|성과\s*달성도|기준별\s*평가결과|결론)\s*$",
        text,
    ))
    ordinals = [int(match.group(1) or match.group(2)) for match in matches]
    if len(matches) != 5 or ordinals != [1, 2, 3, 4, 5]:
        raise AdapterContractError("국문 요약에는 (1)~(5)의 고정 상위 항목이 정확히 한 번씩 있어야 합니다.")
    slots: dict[str, str] = {}
    for index, (block, match) in enumerate(zip(SUMMARY_KO_BLOCKS, matches)):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        slots[block.key] = text[match.end():end].strip()
    return slots


def parse_summary_ko_section(value: object) -> dict[str, str]:
    """Parse either the canonical five-heading draft or its strict JSON envelope."""
    raw = str(value or "").strip()
    slots: dict[str, str]
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AdapterContractError("국문 요약이 유효한 JSON이 아닙니다.") from exc
        if not isinstance(payload, dict):
            raise AdapterContractError("국문 요약 JSON이 객체가 아닙니다.")
        payload_slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else payload
        if payload.get("schema") == "section5_summary_slots_v1":
            slots = _migrate_v1_slots(payload_slots)
        elif payload.get("schema") in {SUMMARY_KO_SCHEMA, None}:
            slots = {str(key): str(item or "") for key, item in payload_slots.items()}
        else:
            raise AdapterContractError(f"국문 요약 schema가 {SUMMARY_KO_SCHEMA}와 일치하지 않습니다.")
    else:
        slots = _parse_plain_document(raw)
    return assert_summary_ko_payload(slots)


def validate_summary_ko_manifest(manifest: object) -> None:
    """Validate the reviewed five-block address/profile manifest."""
    if not isinstance(manifest, dict):
        raise AdapterContractError("국문 요약 슬롯 manifest가 객체가 아닙니다.")
    section = manifest.get("section") if isinstance(manifest.get("section"), dict) else {}
    if int(section.get("section_number") or 0) != SUMMARY_KO_ADAPTER.section_number:
        raise AdapterContractError("국문 요약 manifest의 논리 섹션 번호가 다릅니다.")
    if section.get("section_id") != SUMMARY_KO_ADAPTER.part_id:
        raise AdapterContractError("국문 요약 manifest의 section_id가 다릅니다.")
    if section.get("hwpx_path") != SUMMARY_KO_ADAPTER.hwpx_path:
        raise AdapterContractError("국문 요약 manifest의 물리 XML 경로가 다릅니다.")
    algorithm = manifest.get("algorithm_contract") if isinstance(manifest.get("algorithm_contract"), dict) else {}
    if algorithm.get("input_schema") != SUMMARY_KO_ADAPTER.schema:
        raise AdapterContractError("국문 요약 manifest의 입력 schema가 다릅니다.")
    actual: dict[str, tuple[int, str, str]] = {}
    for item in manifest.get("slots", []):
        if not isinstance(item, dict) or item.get("review_decision") != "candidate":
            continue
        replacement = item.get("replacement") if isinstance(item.get("replacement"), dict) else {}
        key = str(replacement.get("value_key") or "")
        if key:
            actual[key] = (
                int(replacement.get("paragraph_index", -1)),
                str(replacement.get("type") or ""),
                str(replacement.get("heading") or ""),
            )
    if set(actual) != set(SUMMARY_KO_SLOT_KEYS):
        raise AdapterContractError("국문 요약 manifest의 5블록 집합이 계약과 다릅니다.")
    for block in SUMMARY_KO_BLOCKS:
        paragraph_index, replacement_type, heading = actual[block.key]
        if (
            paragraph_index != block.paragraph_index
            or replacement_type != "summary_block"
            or heading != block.heading
        ):
            raise AdapterContractError(f"국문 요약 {block.key} 블록 주소 또는 형식이 올바르지 않습니다.")
