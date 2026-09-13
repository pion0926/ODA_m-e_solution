from __future__ import annotations

from backend.oda_me.reports.context import structured_slots_to_json

from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "project-overview"
MAX_CHARS = 4200

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(context, raw_sections, prepared_sections, _evaluations):
    from ...hwpx_pipeline import _overview_slots
    slots = _overview_slots(context, raw_sections.get(PART_ID, ""), prepared_sections.get(PART_ID, ""))
    return structured_slots_to_json(PART_ID, slots)

def patch_xml(xml, context, prepared_sections): return patch_review_section(7, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=7, part_id=PART_ID, title="사업개요", hwpx_path="Contents/section3.xml",
    mode="overview-table", adapter_id="overview_12_cells", max_chars=MAX_CHARS,
    layout_rule="사업개요 표의 12개 값 셀에 항목별 매핑",
    authoring_shape="반드시 section7_project_overview_slots_v1 schema와 slots를 포함한 JSON을 작성한다. 12개 키 project_name_ko, project_name_en, target_country_region, project_period_budget, project_sector, project_purpose, pcp_feasibility_review, korean_textbook_development, korean_equipment_support, korean_expert_dispatch, korean_invitation_training, partner_contribution을 모두 포함한다. 슬래시는 한 셀 내부의 하위 항목에만 사용하며 서로 다른 슬롯을 하나의 문자열로 합치지 않는다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
