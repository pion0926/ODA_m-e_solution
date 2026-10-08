from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-other"
MAX_CHARS = 4200
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(21, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=21, part_id=PART_ID, title="그 외 평가기준", hwpx_path="Contents/section7.xml",
    mode="criterion", adapter_id="other_criteria_heading_block", max_chars=MAX_CHARS,
    layout_rule="사업 특수 기준만 짧은 하위 문단으로 조판",
    authoring_shape="해당 사업에 실제 적용되는 추가 기준만 기준명·판단·근거·한계 순으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
