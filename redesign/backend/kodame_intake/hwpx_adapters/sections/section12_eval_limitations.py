from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "eval-limitations"
MAX_CHARS = 4500
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(12, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=12, part_id=PART_ID, title="평가의 한계", hwpx_path="Contents/section4.xml",
    mode="narrative", adapter_id="evaluation_limitations_body", max_chars=MAX_CHARS,
    layout_rule="한계-영향-완화조치를 한 묶음으로 조판",
    authoring_shape="각 한계마다 자료공백, 판단에 미치는 영향, 보완 또는 후속조치를 한 묶음으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
