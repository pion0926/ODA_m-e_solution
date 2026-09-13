from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_feedback_table_xml

from ...report_text import sanitize_report_text
from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "feedback"
MAX_CHARS = 8500
def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(_context, raw_sections, prepared_sections, _evaluations):
    raw = sanitize_report_text(raw_sections.get(PART_ID, "")).strip()
    return raw or prepared_sections.get(PART_ID, "")

def patch_xml(xml, context, prepared_sections):
    result = patch_review_section(26, xml, context, prepared_sections)
    return SectionPatchResult(patch_hwpx_feedback_table_xml(result.xml, prepared_sections), result.changed, result.metrics)

ADAPTER = build_adapter(
    number=26, part_id=PART_ID, title="환류과제", hwpx_path="Contents/section8.xml",
    mode="feedback-table", adapter_id="feedback_action_rows", max_chars=MAX_CHARS,
    layout_rule="관찰-조치-주체-사유-우선순위-확인자료를 행 단위 매핑",
    authoring_shape="구분, 관찰/근거, 후속조치, 책임주체, 선정사유/우선순위, 완료기한/점검주기/확인자료 열을 가진 Markdown 표를 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
