from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "eval-team"
MAX_CHARS = 3200
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations): return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)
def patch_xml(xml, context, prepared_sections): return patch_review_section(13, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=13, part_id=PART_ID, title="평가팀 구성 및 시행체계", hwpx_path="Contents/section4.xml",
    mode="narrative", adapter_id="evaluation_team_body", max_chars=MAX_CHARS,
    layout_rule="역할·책임·검토체계를 역할 중심 문단으로 조판",
    authoring_shape="구성원 또는 기관별 역할, 책임, 검토·품질관리 체계를 구분해 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
