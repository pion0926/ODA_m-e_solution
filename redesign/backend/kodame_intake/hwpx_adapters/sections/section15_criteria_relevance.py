from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-relevance"
MAX_CHARS = 7600
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(15, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=15, part_id=PART_ID, title="적절성", hwpx_path="Contents/section6.xml",
    mode="criterion", adapter_id="relevance_heading_block", max_chars=MAX_CHARS,
    layout_rule="수요-정책-설계 판단을 하위 소제목별 문단으로 조판",
    authoring_shape="수요·정책·설계 적합성을 각각 주장-근거-해석-한계 구조의 하위 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
