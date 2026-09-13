from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_cover_slots_only_xml
from backend.oda_me.reports.context import structured_slots_to_json

from ...assessment_context import assessment_date
from ..section_adapter import SectionPatchResult
from ._shared import build_adapter, normalize_with_contract

PART_ID = "cover"
MAX_CHARS = 260


def normalize(value, normalizer):
    return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)


def prepare(context, raw_sections, _prepared_sections, _evaluations):
    lines = [line.strip() for line in raw_sections.get(PART_ID, "").splitlines() if line.strip()]
    manager = next((line for line in lines if line.startswith("평가책임자")), "평가책임자 확인 필요")
    institution = next((line for line in lines if line.startswith("평가수행기관")), "평가수행기관 확인 필요")
    project = context.get("project") or {}
    return structured_slots_to_json(PART_ID, {
        "project_title": str(project.get("title") or "확인 필요"),
        "report_title": str(project.get("report_label") or "평가보고서"),
        "report_date": assessment_date().strftime("%Y. %m"),
        "evaluation_manager": manager,
        "evaluation_institution": institution,
    })


def patch_xml(xml, context, prepared_sections):
    from ...hwpx_layout.cover import wrap_cover_title_xml

    xml, changed = patch_hwpx_cover_slots_only_xml(xml, context, prepared_sections)
    xml, title_wraps = wrap_cover_title_xml(xml, context.get("project") or {})
    return SectionPatchResult(xml, changed, {"title_wraps": title_wraps})


ADAPTER = build_adapter(
    number=1, part_id=PART_ID, title="표지", hwpx_path="Contents/section0.xml",
    mode="cover-slots", adapter_id="cover_fields", max_chars=MAX_CHARS,
    layout_rule="표지의 기존 텍스트 런만 교체",
    authoring_shape="사업명, 보고서명, 기준연월, 평가책임자, 평가수행기관을 각 한 줄로 작성한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml,
    source_module=__name__,
)
