from __future__ import annotations

from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "grade"
MAX_CHARS = 5200

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, raw_sections, prepared_sections, _evaluations):
    from ...hwpx_pipeline import preserve_structured_grade_section
    return preserve_structured_grade_section(raw_sections.get(PART_ID, ""), prepared_sections.get(PART_ID, ""))

def patch_xml(xml, context, prepared_sections): return patch_review_section(4, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=4, part_id=PART_ID, title="평가등급 결과표", hwpx_path="Contents/section2.xml",
    mode="grade-table", adapter_id="grade_result_cells", max_chars=MAX_CHARS,
    layout_rule="평가질문별 점수·산정이유를 원본 표 셀에 압축",
    authoring_shape="평가기준, 점수, 등급, 산정이유 열을 가진 Markdown 표와 짧은 종합판정을 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
