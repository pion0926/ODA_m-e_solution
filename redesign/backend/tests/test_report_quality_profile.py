from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path

from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans, get_hwpx_xml_scope_text
from kodame_intake.hwpx_layout.page_identity import apply_page_identity_xml
from kodame_intake.hwpx_layout.project_overview import (
    CANONICAL_HEADING,
    TABLE_CELL_MARGIN_VERTICAL,
    TABLE_ROW_MIN_HEIGHT,
    compact_project_overview_table_xml,
    normalize_project_overview_opening_xml,
)
from kodame_intake.quality_profile import report_quality_profile
from report_writing_policy import report_writing_policy_issues


class ReportQualityProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[3]
        cls.template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"

    def test_quality_profile_is_user_editable_and_complete(self) -> None:
        profile = report_quality_profile()
        self.assertEqual(profile["version"], 1)
        self.assertEqual(len(profile["layout"]["grade_table"]["page_row_groups"]), 2)
        self.assertEqual(len(profile["layout"]["achievement_table"]["page_item_groups"]), 3)
        self.assertEqual(len(profile["layout"]["evaluation_matrix_table"]["page_row_groups"]), 2)
        self.assertTrue(profile["layout"]["achievement_table"]["preserve_full_cell_text"])
        self.assertFalse(profile["layout"]["page_identity"]["enabled"])
        json.dumps(profile, ensure_ascii=False)

    def test_project_overview_authoring_note_and_empty_run_are_removed(self) -> None:
        with zipfile.ZipFile(self.template, "r") as archive:
            xml = archive.read("Contents/section3.xml").decode("utf-8")
        updated, changed = normalize_project_overview_opening_xml(xml)
        self.assertTrue(changed)
        self.assertNotIn("사업개요서 최종본 사용", get_hwpx_xml_scope_text(updated))
        heading = next(
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:p")
            if get_hwpx_xml_scope_text(updated[start:end]).strip() == CANONICAL_HEADING
            and "<hp:tbl" not in updated[start:end]
        )
        self.assertIn('pageBreak="1"', heading.split(">", 1)[0])

    def test_project_overview_table_uses_compact_vertical_padding(self) -> None:
        with zipfile.ZipFile(self.template, "r") as archive:
            xml = archive.read("Contents/section3.xml").decode("utf-8")
        updated, changed = compact_project_overview_table_xml(xml)
        self.assertTrue(changed)
        table = next(
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:tbl")
            if "사업명(국문)" in get_hwpx_xml_scope_text(updated[start:end])
        )
        margins = __import__("re").findall(r"<hp:cellMargin\b[^>]*/>", table)
        self.assertTrue(margins)
        self.assertTrue(all(
            f'top="{TABLE_CELL_MARGIN_VERTICAL}"' in margin
            and f'bottom="{TABLE_CELL_MARGIN_VERTICAL}"' in margin
            for margin in margins
        ))
        declared = int(
            __import__("re")
            .search(r'<hp:sz\b[^>]*\bheight="(\d+)"', table)
            .group(1)
        )
        self.assertLess(declared, 46085)
        self.assertGreaterEqual(declared, TABLE_ROW_MIN_HEIGHT * 15)
        self.assertIn('treatAsChar="1"', table.split('<hp:tr', 1)[0])
        self.assertIn('pageBreak="CELL"', table.split('>', 1)[0])

    def test_page_identity_removes_mark_but_keeps_page_number_controls(self) -> None:
        with zipfile.ZipFile(self.template, "r") as archive:
            for section_index in range(1, 9):
                section_path = f"Contents/section{section_index}.xml"
                xml = archive.read(section_path).decode("utf-8")
                updated, checks = apply_page_identity_xml(
                    section_path,
                    xml,
                    {"title": "사용자가 편집 가능한 테스트 사업"},
                )
                self.assertTrue(checks["page_number_activated"], section_path)
                self.assertIn('<hp:pageNum pos="BOTTOM_CENTER"', updated, section_path)
                if "<hp:header" in xml:
                    self.assertGreaterEqual(int(checks["identity_controls_removed"]), 1)
                    self.assertTrue(checks["identity_mark_disabled"], section_path)
                    self.assertNotIn("<hp:header", updated)
                    self.assertNotIn("<hp:footer", updated)
                    self.assertNotIn("K-ODAME", get_hwpx_xml_scope_text(updated))

    def test_repetitive_ai_style_is_a_generation_blocker(self) -> None:
        issues = report_writing_policy_issues(
            "- (근거 기반 판단) 첫 문단.\n- (근거 기반 판단) 둘째 문단.\n관련 근거가 확인됨."
        )
        self.assertTrue(any("범용 괄호 라벨 반복" in item for item in issues))
        self.assertTrue(any("상투적 근거 문구" in item for item in issues))


if __name__ == "__main__":
    unittest.main()
