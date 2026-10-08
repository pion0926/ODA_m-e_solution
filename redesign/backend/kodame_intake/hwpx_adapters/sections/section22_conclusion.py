from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "conclusion"
MAX_CHARS = 6200
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(22, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=22, part_id=PART_ID, title="결론", hwpx_path="Contents/section7.xml",
    mode="narrative", adapter_id="conclusion_body", max_chars=MAX_CHARS,
    layout_rule="기준별 판단을 새로운 사실 없이 종합",
    authoring_shape="성과달성도와 기준별 판단을 종합하되 새로운 사실을 추가하지 않고 최종 판단과 핵심 한계를 분리한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
