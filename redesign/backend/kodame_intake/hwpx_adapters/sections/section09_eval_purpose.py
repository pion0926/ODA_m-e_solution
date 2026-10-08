from __future__ import annotations

from backend.oda_me.reports.context import structured_slots_to_json

from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "eval-purpose"
MAX_CHARS = 3600

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, _raw_sections, prepared_sections, _evaluations):
    from ..structured_input import read_slot_input
    parsed = read_slot_input(PART_ID, _raw_sections.get(PART_ID, ""))
    if parsed.detected:
        return structured_slots_to_json(PART_ID, parsed.complete(["evaluation_purpose_scope_body"]))
    return structured_slots_to_json(PART_ID, {"evaluation_purpose_scope_body": prepared_sections.get(PART_ID, "")})

def patch_xml(xml, context, prepared_sections): return patch_review_section(9, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=9, part_id=PART_ID, title="평가의 목적과 범위", hwpx_path="Contents/section4.xml",
    mode="narrative", adapter_id="evaluation_scope_body", max_chars=MAX_CHARS,
    layout_rule="목적·대상·기간·범위·활용을 의미 문단으로 분리",
    authoring_shape="평가목적, 대상, 기준기간, 범위, 핵심질문, 결과 활용을 하위 문단으로 분리한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
