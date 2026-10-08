from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_eval_matrix_table_xml
from backend.oda_me.reports.context import structured_slots_to_json

from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "eval-matrix"
MAX_CHARS = 9500

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, raw_sections, _prepared_sections, evaluations):
    from ...hwpx_pipeline import _matrix_slots
    return structured_slots_to_json(PART_ID, _matrix_slots(raw_sections.get(PART_ID, ""), evaluations))

def patch_xml(xml, context, prepared_sections):
    result = patch_review_section(10, xml, context, prepared_sections)
    return SectionPatchResult(
        patch_hwpx_eval_matrix_table_xml(result.xml, context, prepared_sections),
        result.changed,
        result.metrics,
    )

ADAPTER = build_adapter(
    number=10, part_id=PART_ID, title="평가매트릭스", hwpx_path="Contents/section4.xml",
    mode="matrix-table", adapter_id="evaluation_matrix_32_cells", max_chars=MAX_CHARS,
    layout_rule="기준별 질문-지표-출처-방법 32개 셀 매핑",
    authoring_shape="평가기준, 평가질문, 측정지표/판단기준, 자료출처, 분석방법 열을 가진 Markdown 표를 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
