from io import BytesIO
from pathlib import Path
import json
import re
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

from kodame_intake.report_section_preview import isolate_section_xml, package_single_section, top_level_paragraphs
from kodame_intake.hwpx_adapters.registry import SPEC_BY_PART

ROOT = Path(__file__).resolve().parents[3]
HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'


class SectionPreviewTests(unittest.TestCase):
    def test_preview_prepares_only_selected_adapter(self):
        from kodame_intake.hwpx_pipeline import prepare_hwpx_sections
        from kodame_intake.hwpx_adapters.section_adapter import SectionHwpxAdapter
        calls = []
        def prepare(adapter, *args):
            calls.append(adapter.spec.part_id)
            return 'selected content'
        with patch.object(SectionHwpxAdapter, 'prepare', prepare):
            prepare_hwpx_sections({}, {}, [], selected_parts={'cover'})
        self.assertEqual(calls, ['cover'])
        calls.clear()
        with patch.object(SectionHwpxAdapter, 'prepare', prepare):
            prepare_hwpx_sections({}, {}, [])
        self.assertEqual(len(calls), 27)

    def test_heading_with_inline_line_breaks(self):
        xml = '<hs:sec><hp:p><hp:run><hp:t>other</hp:t></hp:run></hp:p><hp:p><hp:run><hp:t><hp:lineBreak/><hp:lineBreak/>(2) 교훈</hp:t></hp:run></hp:p></hs:sec>'
        selected = isolate_section_xml(xml, 'test', {'test':['(2) 교훈',None]})
        self.assertNotIn('other', selected)
        self.assertIn('(2) 교훈', selected)

    def test_all_27_sections_have_explicit_boundaries(self):
        rules = json.loads((ROOT/'config/report_section_preview.json').read_text(encoding='utf-8'))['boundaries']
        self.assertEqual(set(rules), set(SPEC_BY_PART))

    def test_nested_table_paragraph_is_not_a_section_boundary(self):
        xml = '<hs:sec xmlns:hs="s" xmlns:hp="p"><hp:p><hp:run><hp:secPr/><hp:t>start</hp:t></hp:run></hp:p><hp:p><hp:tbl><hp:p><hp:run><hp:t>end</hp:t></hp:run></hp:p></hp:tbl></hp:p><hp:p><hp:run><hp:t>end</hp:t></hp:run></hp:p></hs:sec>'
        self.assertEqual(len(top_level_paragraphs(xml)), 3)
        selected = isolate_section_xml(xml, 'test', {'test':['start','end']})
        self.assertIn('<hp:tbl>', selected)
        self.assertEqual(len(top_level_paragraphs(selected)), 2)

    def test_missing_boundary_fails_closed(self):
        xml = '<hs:sec><hp:p><hp:run><hp:t>another section</hp:t></hp:run></hp:p></hs:sec>'
        with self.assertRaisesRegex(ValueError, '경계'):
            isolate_section_xml(xml, 'test', {'test':['missing',None]})

    def test_selected_paragraph_keeps_paper_but_not_other_content(self):
        xml = '<hs:sec><hp:p><hp:run><hp:secPr><hp:pagePr width="1"/></hp:secPr><hp:t>private sibling</hp:t></hp:run></hp:p><hp:p pageBreak="1"><hp:run><hp:t>start</hp:t></hp:run></hp:p></hs:sec>'
        selected = isolate_section_xml(xml, 'test', {'test':['start',None]})
        self.assertIn('<hp:secPr>', selected)
        self.assertNotIn('private sibling', selected)
        self.assertIn('pageBreak="0"', selected)

    def test_single_section_package_has_no_sibling_manifest_or_preview(self):
        template = (ROOT/'samples/5-1. 종료평가 결과보고서 placeholder.hwpx').read_bytes()
        with zipfile.ZipFile(BytesIO(template)) as z:
            xml = z.read('Contents/section3.xml').decode('utf-8')
            header = z.read('Contents/header.xml').decode('utf-8')
        from kodame_intake.hwpx_layout.project_overview import normalize_project_overview_opening_xml
        xml, _ = normalize_project_overview_opening_xml(xml)
        selected = isolate_section_xml(xml, 'project-overview')
        data = package_single_section(template, selected, header)
        with zipfile.ZipFile(BytesIO(data)) as z:
            sections = [name for name in z.namelist() if re.fullmatch(r'Contents/section\d+.xml',name)]
            self.assertEqual(sections, ['Contents/section0.xml'])
            manifest = z.read('Contents/content.hpf').decode('utf-8')
            self.assertEqual(len(re.findall(r'href="Contents/section\d+.xml"',manifest)),1)
            self.assertEqual(len(re.findall(r'idref="section\d+"',manifest)),1)
            self.assertIn('secCnt="1"',z.read('Contents/header.xml').decode('utf-8'))
            ET.fromstring(z.read('Contents/section0.xml'))
            ET.fromstring(z.read('Contents/content.hpf'))
            self.assertNotIn('Preview/PrvImage.png',z.namelist())


if __name__ == '__main__':
    unittest.main()
