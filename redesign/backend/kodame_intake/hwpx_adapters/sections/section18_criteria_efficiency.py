from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-efficiency"
MAX_CHARS = 7600
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(18, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=18, part_id=PART_ID, title="효율성", hwpx_path="Contents/section7.xml",
    mode="criterion", adapter_id="efficiency_heading_block", max_chars=MAX_CHARS,
    layout_rule="예산-일정-조달-관리 판단을 문단으로 조판",
    authoring_shape="예산, 일정, 조달, 투입 대비 산출, 관리체계를 각각 하위 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
