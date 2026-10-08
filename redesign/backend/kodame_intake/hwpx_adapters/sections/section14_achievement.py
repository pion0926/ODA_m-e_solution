from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_achievement_table_xml
from ...report_response import normalize_achievement_structure

from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "achievement"
MAX_CHARS = 10000
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)
def prepare(context, raw_sections, prepared_sections, evaluations):
    return normalize_achievement_structure(keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations))

def patch_xml(xml, context, prepared_sections):
    result = patch_review_section(14, xml, context, prepared_sections)
    return SectionPatchResult(patch_hwpx_achievement_table_xml(result.xml, prepared_sections), result.changed, result.metrics)

ADAPTER = build_adapter(
    number=14, part_id=PART_ID, title="성과 달성도", hwpx_path="Contents/section5.xml",
    mode="achievement", adapter_id="achievement_body_and_rows", max_chars=MAX_CHARS,
    layout_rule="서술 본문과 지표 표 입력을 함께 준비",
    authoring_shape="최신 PDM 1건의 Outcome·Output 지표 전체를 성과지표, 기초선, 목표치, 실적, 달성률, 검증수단, 근거 위치, 판단 필드로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
