import unittest

from kodame_intake.hwpx_layout.control_integrity import remove_empty_controls_xml
from kodame_intake.hwpx_layout.page_identity import _remove_identity_controls_xml
from kodame_intake.hwpx_layout.pipeline import finalize_report_section_layout


class ControlIntegrityTests(unittest.TestCase):
    def test_empty_forms_and_idempotence(self):
        source = '<hp:run><hp:ctrl></hp:ctrl><hp:ctrl>\n </hp:ctrl><hp:ctrl/><hp:ctrl id="1" /></hp:run>'
        result, count = remove_empty_controls_xml(source)
        self.assertEqual((result, count), ('<hp:run></hp:run>', 4))
        self.assertEqual(remove_empty_controls_xml(result), (result, 0))

    def test_preserves_populated_controls_and_surrounding_bytes(self):
        source = '<hp:run><hp:ctrl><hp:pageNum pos="BOTTOM_CENTER"/></hp:ctrl><hp:t>사업명</hp:t></hp:run><hp:linesegarray/><hp:tbl id="3"/>'
        self.assertEqual(remove_empty_controls_xml(source), (source, 0))

    def test_identity_removal_cleans_wrapper_but_preserves_page_number(self):
        page = '<hp:ctrl><hp:pageNum pos="BOTTOM_CENTER"/></hp:ctrl>'
        source = '<hp:run><hp:ctrl><hp:header id="2"><hp:subList/></hp:header></hp:ctrl>' + page + '<hp:t>평가 등급 결과표</hp:t></hp:run>'
        result, count = _remove_identity_controls_xml(source)
        self.assertEqual(count, 1)
        self.assertEqual(result, '<hp:run>' + page + '<hp:t>평가 등급 결과표</hp:t></hp:run>')

    def test_shared_wrapper_keeps_other_control(self):
        source = '<hp:ctrl><hp:header id="2"><hp:subList/></hp:header><hp:pageNum/></hp:ctrl>'
        self.assertEqual(_remove_identity_controls_xml(source), ('<hp:ctrl><hp:pageNum/></hp:ctrl>', 1))

    def test_final_pipeline_guard_also_covers_non_identity_sections(self):
        source = '<hp:p><hp:run><hp:ctrl/><hp:t>표지</hp:t></hp:run></hp:p>'
        result = finalize_report_section_layout('Contents/section0.xml', source)
        self.assertNotIn('<hp:ctrl', result.xml)
        self.assertIn('표지', result.xml)
        self.assertEqual(result.checks['empty_controls_removed'], 1)


if __name__ == '__main__':
    unittest.main()
