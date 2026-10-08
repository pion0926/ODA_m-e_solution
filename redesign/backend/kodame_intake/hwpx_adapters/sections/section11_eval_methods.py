from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "eval-methods"
MAX_CHARS = 6000
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(11, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=11, part_id=PART_ID, title="평가방법", hwpx_path="Contents/section4.xml",
    mode="narrative", adapter_id="evaluation_methods_body", max_chars=MAX_CHARS,
    layout_rule="검증된 수행방법만 단계별 문단/항목으로 조판",
    authoring_shape="실제로 증빙된 문헌검토·정량/정성 분석·교차검증 절차만 단계별 하위 문단으로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
