from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "working-factors"
MAX_CHARS = 6200
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(23, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=23, part_id=PART_ID, title="작동요인", hwpx_path="Contents/section7.xml",
    mode="narrative", adapter_id="working_factors_body", max_chars=MAX_CHARS,
    layout_rule="설계-집행-협력-환경 요인을 인과 문단으로 조판",
    authoring_shape="설계, 집행, 협력, 외부환경의 촉진요인을 원인-작동경로-관찰결과 순으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
