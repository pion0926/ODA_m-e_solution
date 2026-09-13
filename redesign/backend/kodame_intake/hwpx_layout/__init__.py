"""Layout-only stages for the final HWPX report export.

Content mapping remains in :mod:`backend.oda_me.hwpx.patchers`.  This package
owns the reader-facing typography, pagination, table legibility, and final
layout contract so those concerns can evolve independently.
"""

from .cover import adapt_cover_title_font_xml, split_cover_title, wrap_cover_title_xml
from .headings import patch_orphan_heading_page_breaks
from .pipeline import (
    HeaderLayoutResult,
    SectionLayoutResult,
    finalize_report_header_layout,
    finalize_report_section_layout,
)
from .rendering import (
    REQUIRED_TOC_KEYS,
    analyze_hwpx,
    orphan_heading_adjustments_from_analysis,
    toc_page_map_from_analysis,
    validate_render_result,
    validate_summary_page_span,
)
from .theory import (
    attach_feedback_headings_to_table_xml,
    force_lessons_page_break_xml,
    replace_stale_theory_pictures_xml,
)
from .toc import clean_toc_annotations_xml, patch_toc_page_numbers
from .validation import validate_orphan_heading_page_breaks, validate_report_layout_contract

__all__ = [
    "HeaderLayoutResult",
    "REQUIRED_TOC_KEYS",
    "SectionLayoutResult",
    "adapt_cover_title_font_xml",
    "analyze_hwpx",
    "attach_feedback_headings_to_table_xml",
    "clean_toc_annotations_xml",
    "finalize_report_header_layout",
    "finalize_report_section_layout",
    "force_lessons_page_break_xml",
    "orphan_heading_adjustments_from_analysis",
    "patch_orphan_heading_page_breaks",
    "patch_toc_page_numbers",
    "replace_stale_theory_pictures_xml",
    "split_cover_title",
    "toc_page_map_from_analysis",
    "validate_report_layout_contract",
    "validate_orphan_heading_page_breaks",
    "validate_render_result",
    "validate_summary_page_span",
    "wrap_cover_title_xml",
]
