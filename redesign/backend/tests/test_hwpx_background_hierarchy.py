import unittest
from kodame_intake.hwpx_layout.background_hierarchy import normalize_background_hierarchy_xml


def paragraph(text):
    return '<hp:p id="1" paraPrIDRef="69" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="28"><hp:t>' + text + '</hp:t></hp:run></hp:p>'


class BackgroundHierarchyTests(unittest.TestCase):
    def test_nested_circle_becomes_separate_detail_without_losing_text(self):
        source = paragraph('1. 사업 추진배경') + paragraph('ㅇ (상위 제목)<hp:lineBreak/>ㅇ (하위 제목) - (근거) 실제 본문임.') + paragraph('2. 사업개요')
        result, count = normalize_background_hierarchy_xml(source)
        self.assertEqual(count, 1)
        self.assertIn('- (하위 제목) (근거) 실제 본문임.', result)
        self.assertEqual(result.count('ㅇ'), 1)
        self.assertIn('paraPrIDRef="92"', result)
        self.assertEqual(normalize_background_hierarchy_xml(result), (result, 0))

    def test_unrelated_sections_unchanged(self):
        source = paragraph('ㅇ (상위 제목)ㅇ (하위 제목) - 본문임.')
        self.assertEqual(normalize_background_hierarchy_xml(source), (source, 0))

    def test_identical_title_is_not_repeated_in_detail(self):
        source = paragraph('1. 사업 추진배경') + paragraph('ㅇ (정부 정책)ㅇ (정부 정책) - (근거) 본문임.')
        result, count = normalize_background_hierarchy_xml(source)
        self.assertEqual(count, 1)
        self.assertEqual(result.count('(정부 정책)'), 1)
        self.assertIn('- (근거) 본문임.', result)
