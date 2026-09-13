from __future__ import annotations

from dataclasses import dataclass, field

from backend.oda_me.hwpx.patchers import patch_hwpx_report_outline_header_xml

from .cover import adapt_cover_title_font_xml
from .control_integrity import remove_empty_controls_xml
from .background_hierarchy import normalize_background_hierarchy_xml
from .cell_wrapping import normalize_table_cell_wrapping
from .achievement_readability import improve_achievement_readability
from .headings import (
    force_numbered_criterion_page_breaks_xml,
    normalize_heading_hierarchy_xml,
    patch_heading_pagination_header_xml,
    style_project_background_subheadings_xml,
)
from .grade_table import style_grade_table_xml
from .page_identity import apply_page_identity_xml
from .project_overview import (
    compact_project_overview_table_xml,
    normalize_project_overview_opening_xml,
)
from .recommendations import style_recommendation_tables_xml
from .spacing import (
    EVALUATION_OVERVIEW_CHAPTER_HEADING,
    ensure_blank_line_before_report_headings_xml,
    ensure_page_break_before_heading_xml,
)
from .tables import (
    detach_evaluation_matrix_table_xml,
    style_achievement_table_xml,
    style_evaluation_matrix_heading_spacing_xml,
    style_evaluation_matrix_header_xml,
    style_evaluation_matrix_table_xml,
    style_pdm_table_xml,
)
from .theory import (
    attach_feedback_headings_to_table_xml,
    force_lessons_page_break_xml,
    replace_stale_theory_pictures_xml,
)
from .toc import patch_toc_header_layout, normalize_toc_tab_widths_xml, normalize_toc_page_number_spacing_xml
from .typography import normalize_report_text_colors_header_xml


@dataclass(frozen=True)
class HeaderLayoutResult:
    xml: str
    cover_font_height: int
    text_colors_normalized: int = 0


@dataclass(frozen=True)
class SectionLayoutResult:
    xml: str
    checks: dict[str, bool | int] = field(default_factory=dict)


def finalize_report_header_layout(xml: str, project: dict) -> HeaderLayoutResult:
    """Apply independent cover, outline-indent, and pagination policies."""

    xml, cover_font_height = adapt_cover_title_font_xml(xml, project)
    xml = patch_hwpx_report_outline_header_xml(xml)
    xml = patch_heading_pagination_header_xml(xml)
    xml, _ = patch_toc_header_layout(xml)
    xml, text_colors_normalized = normalize_report_text_colors_header_xml(xml)
    return HeaderLayoutResult(
        xml=xml,
        cover_font_height=cover_font_height,
        text_colors_normalized=text_colors_normalized,
    )


def finalize_report_section_layout(
    section_path: str,
    xml: str,
    project: dict | None = None,
    theory_png: bytes | None = None,
) -> SectionLayoutResult:
    """Dispatch section-specific layout passes after all content is written."""

    checks: dict[str, bool | int] = {}
    if section_path == "Contents/section1.xml":
        xml, checks["toc_number_spacing"] = normalize_toc_page_number_spacing_xml(xml)
        xml, checks["toc_tab_widths"] = normalize_toc_tab_widths_xml(xml)
    if section_path == "Contents/section2.xml":
        xml, checks["grade_split_layout"] = style_grade_table_xml(xml)
    elif section_path == "Contents/section3.xml":
        xml, checks["project_chapter_fresh_page"] = ensure_page_break_before_heading_xml(
            xml, "II. 대상사업개요"
        )
        xml, checks["project_overview_opening"] = normalize_project_overview_opening_xml(xml)
        xml, checks["project_overview_table_compacted"] = compact_project_overview_table_xml(xml)
        xml, checks["project_background_subheadings"] = style_project_background_subheadings_xml(xml)
        xml, checks["project_background_hierarchy"] = normalize_background_hierarchy_xml(xml)
    elif section_path == "Contents/section4.xml":
        xml, checks["pdm_typography"] = style_pdm_table_xml(xml)
        xml, checks["evaluation_matrix_header"] = style_evaluation_matrix_header_xml(xml)
        xml, checks["evaluation_matrix_detached"] = detach_evaluation_matrix_table_xml(xml)
        xml, checks["evaluation_matrix_heading_spacing"] = style_evaluation_matrix_heading_spacing_xml(xml)
        xml, checks["evaluation_matrix_layout"] = style_evaluation_matrix_table_xml(xml)
        xml, checks["evaluation_overview_fresh_page"] = ensure_page_break_before_heading_xml(
            xml,
            EVALUATION_OVERVIEW_CHAPTER_HEADING,
        )
    elif section_path == "Contents/section5.xml":
        xml, checks["achievement_typography"] = style_achievement_table_xml(xml)
        xml, checks["achievement_readability"] = improve_achievement_readability(xml)
    elif section_path == "Contents/section8.xml":
        xml, kept, removed = replace_stale_theory_pictures_xml(xml, theory_png)
        checks["theory_picture_kept"] = kept
        checks["theory_picture_removed"] = removed
        xml, checks["feedback_headings_attached"] = attach_feedback_headings_to_table_xml(xml)
        xml, checks["lessons_page_break"] = force_lessons_page_break_xml(xml)
        xml, recommendation_checks = style_recommendation_tables_xml(xml)
        checks.update(recommendation_checks)

    if section_path in {"Contents/section6.xml", "Contents/section7.xml"}:
        xml, checks["criterion_page_breaks"] = force_numbered_criterion_page_breaks_xml(xml)

    if section_path not in {"Contents/section0.xml", "Contents/section1.xml"}:
        xml, checks["blank_line_before_report_headings"] = (
            ensure_blank_line_before_report_headings_xml(xml)
        )

    xml, heading_stats = normalize_heading_hierarchy_xml(xml)
    checks["major_chapters_normalized"] = heading_stats.major_chapters
    checks["section_headings_normalized"] = heading_stats.section_headings
    xml, identity_checks = apply_page_identity_xml(section_path, xml, project)
    checks.update(identity_checks)
    xml, checks["table_cell_wrapping_normalized"] = normalize_table_cell_wrapping(xml)
    xml, checks["empty_controls_removed"] = remove_empty_controls_xml(xml)
    return SectionLayoutResult(xml=xml, checks=checks)
