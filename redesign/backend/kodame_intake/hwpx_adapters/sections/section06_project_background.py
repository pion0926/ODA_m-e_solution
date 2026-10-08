from __future__ import annotations

from backend.oda_me.reports.context import structured_slots_to_json

from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "project-background"
MAX_CHARS = 5200

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, raw_sections, prepared_sections, _evaluations):
    from ...hwpx_pipeline import _background_slots
    return structured_slots_to_json(PART_ID, _background_slots(raw_sections.get(PART_ID, "") or prepared_sections.get(PART_ID, "")))

def patch_xml(xml, context, prepared_sections): return patch_review_section(6, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=6, part_id=PART_ID, title="사업 추진배경", hwpx_path="Contents/section3.xml",
    mode="background-slots", adapter_id="background_5_paragraphs", max_chars=MAX_CHARS,
    layout_rule="배경 논리를 5개 ㅇ 걸어쓰기 문단으로 렌더링하고 소제목 뒤에서 본문을 줄바꿈",
    authoring_shape="개발문제, 정부정책, 대상지역 수요, ODA 정합성, 사업선정 논리의 다섯 문단을 `(소제목) 본문`으로 작성하며 HWPX에서는 `ㅇ (소제목)` 다음 줄에 본문이 이어진다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
