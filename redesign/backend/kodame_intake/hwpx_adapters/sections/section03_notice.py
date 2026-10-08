from __future__ import annotations

import re
from html import unescape

from backend.oda_me.hwpx.patchers import (
    get_hwpx_xml_scope_text,
    find_hwpx_all_tag_spans,
    clone_hwpx_paragraph_for_semantic_lines,
)
from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "notice"
MAX_CHARS = 1500

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections):
    # Metadata slots remain template-owned, but the editable notice body must
    # come from the saved draft in both the preview and the full export.
    result = patch_review_section(3, xml, context, prepared_sections)
    body = str(prepared_sections.get(PART_ID) or "").strip()
    if not body:
        return result
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    patched, changed = result.xml, 0
    # The notice lives inside a one-cell template table, so outer-only
    # paragraph traversal would silently skip this slot.
    for start, end in find_hwpx_all_tag_spans(patched, "hp:p"):
        paragraph = patched[start:end]
        if "<hp:tbl" in paragraph:
            continue
        text = get_hwpx_xml_scope_text(paragraph)
        if all(part in text for part in ("책임 평가자(", "평가내용 및 편집 일체")):
            replacement = clone_hwpx_paragraph_for_semantic_lines(paragraph, lines)
            patched = patched[:start] + replacement + patched[end:]
            changed = 1
            break
    compact = lambda value: re.sub(r"\s+", "", unescape(value))
    visible = compact(get_hwpx_xml_scope_text(patched))
    if any(compact(line) not in visible for line in lines):
        raise ValueError("평가보고서 관련 공지: 저장된 본문이 양식에 반영되지 않았습니다.")
    return SectionPatchResult(patched, result.changed + changed, {"notice_body_lines": len(lines)})

ADAPTER = build_adapter(
    number=3, part_id=PART_ID, title="평가보고서 관련 공지", hwpx_path="Contents/section2.xml",
    mode="notice-slots", adapter_id="notice_and_reviewers", max_chars=MAX_CHARS,
    layout_rule="공지 상자의 본문은 저장된 문단 그대로 반영하고 검토자·평가일 등 메타데이터 칸은 유지",
    authoring_shape="공개범위·면책·개인정보·인용 주의사항과 검토자 정보를 서로 구분된 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
