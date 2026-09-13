from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-effectiveness"
MAX_CHARS = 9000
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(17, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=17, part_id=PART_ID, title="효과성", hwpx_path="Contents/section6.xml",
    mode="criterion", adapter_id="effectiveness_heading_block", max_chars=MAX_CHARS,
    layout_rule="산출-성과-포용-기여요인을 의미 문단으로 조판",
    authoring_shape="산출, 성과, 포용성, 기여·저해요인을 각각 하위 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
