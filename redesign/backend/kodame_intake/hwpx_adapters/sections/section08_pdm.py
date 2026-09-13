from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_pdm_table_xml
from backend.oda_me.reports.context import structured_slots_to_json

from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "pdm"
MAX_CHARS = 7500

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(context, raw_sections, prepared_sections, _evaluations):
    from ...hwpx_pipeline import _pdm_slots
    slots = _pdm_slots(context, raw_sections.get(PART_ID, ""), prepared_sections.get(PART_ID, ""))
    return structured_slots_to_json(PART_ID, slots)

def patch_xml(xml, context, prepared_sections):
    result = patch_review_section(8, xml, context, prepared_sections)
    return SectionPatchResult(patch_hwpx_pdm_table_xml(result.xml, prepared_sections), result.changed, result.metrics)

ADAPTER = build_adapter(
    number=8, part_id=PART_ID, title="사업설계매트릭스(PDM)", hwpx_path="Contents/section4.xml",
    mode="pdm-table", adapter_id="pdm_15_cells", max_chars=MAX_CHARS,
    layout_rule="목표-지표-MOV-가정의 15개 셀에 계층별 매핑",
    authoring_shape="구분, 요약, 검증지표(OVI), 검증수단(MOV), 중요가정 열과 영향·성과·산출·활동·투입·전제조건 행을 가진 Markdown 표를 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
