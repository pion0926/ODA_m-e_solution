"""Regression for KNUT floating overview table overpainting long background."""
from pathlib import Path
import re
import unittest
import zipfile
import xml.etree.ElementTree as ET

from backend.oda_me.hwpx.patchers import find_hwpx_table_span_by_text, find_hwpx_tag_spans, get_hwpx_xml_scope_text
from kodame_intake.hwpx_layout.project_overview import compact_project_overview_table_xml, normalize_project_overview_opening_xml


ROOT = Path(__file__).resolve().parents[3]


class OverviewFlowTests(unittest.TestCase):
    def test_overview_height_is_content_driven_and_idempotent(self):
        with zipfile.ZipFile(ROOT / 'samples/5-1. 종료평가 결과보고서 placeholder.hwpx') as archive:
            source = archive.read('Contents/section3.xml').decode('utf-8')
        from kodame_intake.hwpx_layout.project_overview import _cell_required_height
        first, _ = compact_project_overview_table_xml(source)
        second, changed = compact_project_overview_table_xml(first)
        self.assertEqual(first, second)
        self.assertFalse(changed)
        _, _, table = find_hwpx_table_span_by_text(first, ['내용', '사업개요', '사업명(국문)'], 20)
        for start, end in find_hwpx_tag_spans(table, 'hp:tc'):
            cell = table[start:end]
            height = int(re.search(r'<hp:cellSz\b[^>]*height="(\d+)"', cell).group(1))
            self.assertGreaterEqual(height, _cell_required_height(cell))
        self.assertIn('width="2600"', table)

    def test_wrapped_cell_expands_instead_of_squeezing_text(self):
        from kodame_intake.hwpx_layout.project_overview import _cell_required_height
        def cell(body):
            return '<hp:tc><hp:p><hp:run><hp:t>' + body + '</hp:t></hp:run></hp:p><hp:cellSz width="10000" height="1500"/></hp:tc>'
        self.assertGreater(_cell_required_height(cell('내용을 보존함. ' * 40)), _cell_required_height(cell('짧은 내용')) * 10)

    def test_variable_background_does_not_leave_floating_overview_anchor(self):
        with zipfile.ZipFile(ROOT / 'samples/5-1. 종료평가 결과보고서 placeholder.hwpx') as archive:
            original = archive.read('Contents/section3.xml').decode('utf-8')
        _, _, original_table = find_hwpx_table_span_by_text(original, ['내용', '사업개요', '사업명(국문)'], 20)
        heading_start = next(start for start, end in find_hwpx_tag_spans(original, 'hp:p') if get_hwpx_xml_scope_text(original[start:end]).strip().startswith('2. 사업개요') and '<hp:tbl' not in original[start:end])
        for repeats in (1, 50, 500):
            # Place long prose before the overview without changing its slot
            # addresses; neither its size nor page count is used by the policy.
            extra = '<hp:p id="30301000" paraPrIDRef="71" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="28"><hp:t>' + '가변 사업배경 본문을 보존함. ' * repeats + '</hp:t></hp:run></hp:p>'
            source = original[:heading_start] + extra + original[heading_start:]
            result, _ = normalize_project_overview_opening_xml(source)
            result, _ = compact_project_overview_table_xml(result)
            ET.fromstring(result)
            _, _, table = find_hwpx_table_span_by_text(result, ['내용', '사업개요', '사업명(국문)'], 20)
            position = re.search(r'<hp:pos\b[^>]*/>', table).group()
            self.assertIn('treatAsChar="1"', position)
            self.assertIn('flowWithText="1"', position)
            self.assertIn('allowOverlap="0"', position)
            self.assertIn('pageBreak="CELL"', table.split('>', 1)[0])
            self.assertEqual(get_hwpx_xml_scope_text(table), get_hwpx_xml_scope_text(original_table))
            self.assertEqual(result.count('가변 사업배경 본문을 보존함.'), repeats)


if __name__ == '__main__':
    unittest.main()
