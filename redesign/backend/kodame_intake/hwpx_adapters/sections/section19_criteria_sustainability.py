from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-sustainability"
MAX_CHARS = 7600
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(19, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=19, part_id=PART_ID, title="지속가능성", hwpx_path="Contents/section7.xml",
    mode="criterion", adapter_id="sustainability_heading_block", max_chars=MAX_CHARS,
    layout_rule="제도-재원-조직-역량-유지관리 문단으로 조판",
    authoring_shape="제도, 재원, 조직, 역량, 유지관리, 현지 소유권을 각각 하위 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
