from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_lessons_table_xml

from ...report_text import sanitize_report_text
from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "lessons"
MAX_CHARS = 7500
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, raw_sections, prepared_sections, _evaluations):
    raw = sanitize_report_text(raw_sections.get(PART_ID, "")).strip()
    return raw or prepared_sections.get(PART_ID, "")

def patch_xml(xml, context, prepared_sections):
    result = patch_review_section(27, xml, context, prepared_sections)
    return SectionPatchResult(patch_hwpx_lessons_table_xml(result.xml, prepared_sections), result.changed, result.metrics)

ADAPTER = build_adapter(
    number=27, part_id=PART_ID, title="교훈", hwpx_path="Contents/section8.xml",
    mode="lessons-table", adapter_id="lesson_rows", max_chars=MAX_CHARS,
    layout_rule="교훈 제목-일반화 원칙-체크리스트를 행 단위 매핑",
    authoring_shape="교훈 제목, 교훈 내용, 일반화 조건/분야, 중복 여부, 후속 체크리스트 열을 가진 Markdown 표를 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
