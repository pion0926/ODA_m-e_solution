from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "criteria-crosscutting"
MAX_CHARS = 6000
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(20, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=20, part_id=PART_ID, title="범분야 이슈", hwpx_path="Contents/section7.xml",
    mode="criterion", adapter_id="crosscutting_heading_block", max_chars=MAX_CHARS,
    layout_rule="젠더-환경-인권-취약계층을 근거 범위별 조판",
    authoring_shape="젠더, 인권·취약계층, 환경·기후, 세이프가드를 근거가 있는 범위에서 구분한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
