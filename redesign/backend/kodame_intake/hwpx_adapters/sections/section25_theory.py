from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "theory"
MAX_CHARS = 6800
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(25, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=25, part_id=PART_ID, title="변화이론 분석", hwpx_path="Contents/section8.xml",
    mode="narrative", adapter_id="theory_of_change_body", max_chars=MAX_CHARS,
    layout_rule="투입-활동-산출-성과 경로와 가정을 문단화",
    authoring_shape="투입-활동-산출-성과-영향 경로, 핵심 가정, 작동/비작동 지점을 구분해 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
