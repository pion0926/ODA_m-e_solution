import re
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans, get_hwpx_xml_scope_text, patch_hwpx_achievement_table_xml,
)
from kodame_intake.hwpx_layout.tables import style_achievement_table_xml, ACHIEVEMENT_FIRST_PAGE_HEIGHT
from kodame_intake.hwpx_layout.overflow import append_table_details
from kodame_intake.hwpx_layout.overflow import resolve_detail_text


class OverflowTests(unittest.TestCase):
    def test_detail_heading_only_continues_on_next_page_and_body_is_regular(self):
        result = append_table_details('', [('PDM 상세 P1', '\n'.join('활동 내용' for _ in range(16)))])
        self.assertEqual(result.count('PDM 상세 P1'), 1)
        self.assertIn('charPrIDRef="85"><hp:t>PDM 상세 P1', result)
        self.assertIn('charPrIDRef="92"><hp:t>활동 내용', result)

    def test_activity_wrapping_and_source_number_discrepancy_are_explicit(self):
        from kodame_intake.hwpx_layout.pdm_text import activity_display_text
        text = '1.1.1. 활동(1.1.1.) : 현지 교원 단독 강의\n모니터링\n1.1.2. 활동(1.1.1.) : 교육과정\n인증 추진'
        self.assertEqual(activity_display_text(text), '1.1.1. 현지 교원 단독 강의 모니터링\n1.1.2. [원문 활동번호: 1.1.1] 교육과정 인증 추진')

    def test_grade_table_grows_pages_without_losing_question_reasons(self):
        from backend.oda_me.hwpx.patchers import (
            find_hwpx_grade_table_span_xml, set_hwpx_table_cell_text_xml, GRADE_QUESTION_REASON_CELLS,
        )
        from kodame_intake.hwpx_layout.grade_table import style_grade_table_xml
        path=Path(__file__).resolve().parents[3]/'samples'/'5-1. 종료평가 결과보고서 placeholder.hwpx'
        with zipfile.ZipFile(path) as archive:
            xml=archive.read('Contents/section2.xml').decode('utf-8')
        start,end=find_hwpx_grade_table_span_xml(xml)
        table=xml[start:end]
        reasons=[]
        for index,cell in enumerate(GRADE_QUESTION_REASON_CELLS):
            reason=f'질문{index} ' + '확인된 자료가 부족하여 판단을 보류하며 추가 자료 확보가 필요하다. '*5
            reasons.append(reason)
            table,_=set_hwpx_table_cell_text_xml(table,cell,reason)
        result,_=style_grade_table_xml(xml[:start]+table+xml[end:])
        ET.fromstring(result)
        tables=[result[a:b] for a,b in find_hwpx_tag_spans(result,'hp:tbl')
                if '핵심 질문' in get_hwpx_xml_scope_text(result[a:b])]
        self.assertGreater(len(tables),2)
        for index,table in enumerate(tables):
            self.assertLessEqual(int(re.search(r'<hp:sz\b[^>]*height="(\d+)"',table)[1]),58000 if index==0 else 65000)
        visible=get_hwpx_xml_scope_text(result)
        for reason in reasons:
            self.assertIn(reason.strip(),visible)

    def test_named_bracket_indicators_stay_separate(self):
        from backend.oda_me.hwpx.patchers import parse_achievement_items, achievement_item_fields
        content = '\n'.join(f'- [{i}-1 지표 이름]: 성과지표: 지표{i} / 기초선: 0 / 목표치: 10 / 종료선 또는 현재 실적: {i} / 대비 결과: 진행 / 지표입증수단(MOV): 문서{i} / 비고: 원문{i}' for i in range(1, 15))
        rows = parse_achievement_items(content)
        self.assertEqual(len(rows), 14)
        for i, row in enumerate(rows, 1):
            fields = achievement_item_fields(row, i - 1)
            self.assertEqual(fields['indicator'], f'지표{i}')
            self.assertEqual(fields['note'], f'원문{i}')

    def test_other_long_table_cells_are_relocated_without_loss(self):
        from backend.oda_me.hwpx.patchers import find_hwpx_table_span_by_text, set_hwpx_table_cell_text_xml
        from kodame_intake.hwpx_layout.tables import style_pdm_table_xml, style_evaluation_matrix_table_xml
        from kodame_intake.hwpx_layout.project_overview import compact_project_overview_table_xml
        path = Path(__file__).resolve().parents[3] / 'samples' / '5-1. 종료평가 결과보고서 placeholder.hwpx'
        cases = [
            ('Contents/section4.xml', ['프로그램 요약', '객관적 검증지표', '중요가정'], 5, style_pdm_table_xml),
            ('Contents/section4.xml', ['분석방법', '평가질문', '적절성'], 6, style_evaluation_matrix_table_xml),
            ('Contents/section3.xml', ['내용', '사업개요', '사업명(국문)'], 4, compact_project_overview_table_xml),
        ]
        with zipfile.ZipFile(path) as archive:
            for section, needles, index, style in cases:
                with self.subTest(section=section, table=needles[0]):
                    xml = archive.read(section).decode('utf-8')
                    a,b,table = find_hwpx_table_span_by_text(xml, needles, 20)
                    value = '긴 원문 자료 Ω & 검증 ' * 1200 + '마지막원문'
                    table, _ = set_hwpx_table_cell_text_xml(table, index, value)
                    result, _ = style(xml[:a] + table + xml[b:])
                    root = ET.fromstring(result)
                    text = ''.join(node.text or '' for node in root.iter() if node.tag.endswith('}t')
                                   and not re.match(r'.* 상세 [A-Z]\d+', node.text or ''))
                    if needles[0] == '분석방법':
                        from kodame_intake.report_exporter import _evaluation_matrix_cell_texts
                        self.assertNotIn('평가매트릭스 상세 M', result)
                        self.assertNotRegex(result, r'\[M\d+ 상세\]')
                        self.assertEqual(_evaluation_matrix_cell_texts(result)[index], value.strip())
                    else:
                        self.assertIn(re.sub(r'\s+', '', value), re.sub(r'\s+', '', text))

    def test_reference_validation_rejects_missing_details(self):
        with self.assertRaises(ValueError):
            resolve_detail_text('', '부분 [M1 상세]')
        value = '실제문서기준 ' * 200
        fragment = append_table_details('', [('평가매트릭스 상세 M1', value)])
        self.assertEqual(resolve_detail_text(fragment, '[M1 상세]'), value)

    def test_current_feedback_authoring_columns(self):
        from backend.oda_me.hwpx.patchers import parse_feedback_items
        rows = parse_feedback_items('| 구분 | 관찰·근거 | 후속조치 | 책임주체 |\n|---|---|---|---|\n| 관리 | 원문 근거 | 확인 조치 | 담당 기관 |')
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['task'], rows[0]['owner'], rows[0]['observation']), ('확인 조치', '담당 기관', '원문 근거'))

    def test_long_all_fields_preserved_and_table_fits(self):
        path = Path(__file__).resolve().parents[3] / 'samples' / '5-1. 종료평가 결과보고서 placeholder.hwpx'
        with zipfile.ZipFile(path) as archive:
            xml = archive.read('Contents/section5.xml').decode('utf-8')
        values = [(f'검증항목{i} 가나다 Ω🙂 & <원문> ' * 180) + f'끝부분{i}' for i in range(7)]
        record = ('- [1.1-1] 성과지표: ' + values[0] + ' / 기초선: ' + values[1]
                  + ' / 목표치: ' + values[2] + ' / 종료선 또는 현재 실적: ' + values[3]
                  + ' / 대비 결과: ' + values[4] + ' / 지표입증수단(MOV): ' + values[5]
                  + ' / 비고: ' + values[6])
        xml = patch_hwpx_achievement_table_xml(xml, {'achievement': record})
        result, changed = style_achievement_table_xml(xml)
        self.assertTrue(changed)
        root = ET.fromstring(result)
        visible = re.sub(r'\s+', '', ''.join(node.text or '' for node in root.iter()
            if node.tag.endswith('}t') and not (node.text or '').startswith('성과지표 상세')))
        for value in values:
            self.assertIn(re.sub(r'\s+', '', value), visible)
        for a, b in find_hwpx_tag_spans(result, 'hp:tbl'):
            table = result[a:b]
            if '성과지표' in get_hwpx_xml_scope_text(table):
                self.assertLessEqual(int(re.search(r'<hp:sz\b[^>]*height="(\d+)"', table)[1]), ACHIEVEMENT_FIRST_PAGE_HEIGHT)
        self.assertIn('성과지표 상세', result)

    def test_detail_preserves_newlines_unicode_and_xml_characters(self):
        text = '\n' + ('가&<나>🙂\n\n' * 1000)
        result = append_table_details('', [('연결 상세 1', text)])
        root = ET.fromstring('<r xmlns:hp="urn:hp"><hp:p><hp:run>' + result + '</hp:run></hp:p></r>')
        contents = [node.text or '' for node in root.iter('{urn:hp}t')]
        self.assertEqual(''.join(value for value in contents if not value.startswith('연결 상세 1')), text)
        self.assertGreater(result.count('pageBreak="1"'), 2)

    def test_short_details_share_pages_without_trailing_blank_page(self):
        details = [(f'평가매트릭스 상세 M{i}', f'질문 {i}의 검토 근거와 한계를 완전히 보존함.') for i in range(1, 13)]
        result = append_table_details('', details)
        self.assertEqual(result.count('pageBreak="1"'), 1)
        root = ET.fromstring('<r xmlns:hp="urn:hp"><hp:p><hp:run>' + result + '</hp:run></hp:p></r>')
        self.assertEqual(list(root)[-1].get('pageBreak'), '0')
        for reference, text in details:
            code = reference.rsplit(' ', 1)[-1]
            self.assertEqual(resolve_detail_text(result, f'[{code} 상세]'), text)

    def test_detail_page_budget_is_shared_across_short_and_long_entries(self):
        details = [('평가매트릭스 상세 M1', '첫 근거'), ('평가매트릭스 상세 M2', '원문가나다'*800), ('평가매트릭스 상세 M3', '끝 근거')]
        result = append_table_details('', details)
        self.assertLess(result.count('pageBreak="1"'), 8)
        for reference, text in details:
            self.assertEqual(resolve_detail_text(result, '[' + reference.rsplit(' ', 1)[-1] + ' 상세]'), text)
