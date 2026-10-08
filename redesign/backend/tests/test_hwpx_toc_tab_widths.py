import unittest
from kodame_intake.hwpx_layout.toc import normalize_toc_tab_widths_xml


class TocTabWidthTests(unittest.TestCase):
    def test_keeps_vertical_cache_and_page_value(self):
        source = '<hp:p id="1"><hp:run charPrIDRef="80"><hp:t>1. 국문 요약<hp:tab width="33800" leader="3" type="2"/></hp:t></hp:run><hp:run charPrIDRef="61"><hp:t>6</hp:t></hp:run><hp:linesegarray><hp:lineseg vertpos="7844"/></hp:linesegarray></hp:p>'
        expected = source.replace('type="2"', 'type="1"')
        self.assertEqual(normalize_toc_tab_widths_xml(source), (expected, 1))
        self.assertEqual(normalize_toc_tab_widths_xml(expected), (expected, 0))

    def test_unrelated_tabs_are_not_changed(self):
        source = '<hp:p><hp:run><hp:t>본문<hp:tab width="33800"/>내용</hp:t></hp:run></hp:p>'
        self.assertEqual(normalize_toc_tab_widths_xml(source), (source, 0))

    def test_zero_width_center_tab_still_requires_right_alignment(self):
        source = '<hp:p><hp:run><hp:t>1. 국문 요약<hp:tab width="0" leader="3" type="2"/></hp:t></hp:run><hp:run><hp:t>6</hp:t></hp:run></hp:p>'
        result, count = normalize_toc_tab_widths_xml(source)
        self.assertEqual(count, 1)
        self.assertEqual(result, source.replace('type="2"', 'type="1"'))
