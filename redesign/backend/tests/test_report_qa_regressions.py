import unittest

from kodame_intake.report_generator import _quantitative_consistency_issues
from kodame_intake.report_rhwp_verification import DESTINATIONS, rhwp_page_map
from kodame_intake.hwpx_layout.tables import achievement_page_groups
from kodame_intake.report_response import normalize_achievement_structure
from backend.oda_me.hwpx.patchers import parse_achievement_items, achievement_item_fields


class ReportQaRegressions(unittest.TestCase):
    def test_multiline_indicator_records_keep_summary_heading(self):
        text='ㅇ 성과지표: 강사 수\n- 목표치: 6명\n- 실적: 6명\n\nㅇ 산출물 달성 현황과 시사점\n- 후속 예산 확인 필요'
        normalized=normalize_achievement_structure(text)
        self.assertIn('3. 종합 평가 및 시사점\n\nㅇ 산출물',normalized)
        self.assertEqual(normalize_achievement_structure(normalized),normalized)

    def test_pdm_display_labels_do_not_turn_detail_bullets_into_rows(self):
        content = ''
        for label in ['Outcome 1-1', 'Outputs 1.1-1']:
            content += f'- [{label}] 지표: 성과지표: 지표명 / 기초선: 0 / 목표치: 10 / 실적: 6 / 비고: 진행 중\n- 후속 과제 설명\n\n'
        content += '3. 종합 평가 및 시사점\nㅇ 종합 진단\n- 추가 분석'
        rows = parse_achievement_items(content)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('성과지표: 지표명' in row for row in rows))
        self.assertTrue(all('추가 분석' not in row and '후속 과제 설명' not in row for row in rows))

    def test_indexed_rows_do_not_absorb_analysis_or_adjacent_records(self):
        text = 'ㅇ 평가 방향\n- 분석임.\n'
        for i in range(12):
            text += f'- [outcome-{i}] 제목: 성과지표: 지표{i} / 기초선: 0 / 목표치: 학생용 5권 / 강사용 1권 / 종료선 또는 현재 실적: 6명 / 대비 결과: 60% / 지표입증수단(MOV): 명부 / 비고: 확인함\n'
        text += '\nㅇ 분석\n- 해석임.'
        rows = parse_achievement_items(text)
        self.assertEqual(len(rows), 12)
        for i, row in enumerate(rows):
            fields = achievement_item_fields(row, i)
            self.assertEqual(fields['indicator'], f'지표{i}')
            self.assertEqual(fields['endline'], '6명')
            self.assertEqual(fields['target'], '학생용 5권 / 강사용 1권')
            self.assertNotIn('해석임', row)

    def test_achievement_analysis_heading_is_idempotent(self):
        content = '- [outcome-1] 성과지표: 지표 / 실적: 확인 필요\n\nㅇ 주요 성과\n- 근거임.'
        normalized = normalize_achievement_structure(content)
        self.assertIn('3. 종합 평가 및 시사점\n\nㅇ 주요 성과', normalized)
        self.assertEqual(normalize_achievement_structure(normalized), normalized)

    def test_every_indicator_is_partitioned_once(self):
        for count in (1, 5, 12, 14, 20):
            groups = achievement_page_groups(count)
            self.assertEqual([i for group in groups for i in group], list(range(count)))
            self.assertTrue(all(1 <= len(group) <= 5 for group in groups))

    def test_current_seven_column_rate(self):
        self.assertTrue(_quantitative_consistency_issues('achievement', '| 강사 수 | 0 | 10명 | 6명 | 90% | 명부 | 진행 |', []))
        self.assertFalse(_quantitative_consistency_issues('achievement', '| 강사 수 | 0 | 10명 | 6명 | 60% | 명부 | 진행 |', []))

    def test_indicator_not_replaced_by_unrelated_quantity(self):
        for row in (
            '| 월평균 교육 인원 (명) | 0 | 4회 | 6회 | 150% | 일지 | 완료 |',
            '| 장비 가동률 및 유지보수 건수 | 0 | 87건 | 188건 도입 및 검수 | 216% | 조서 | 완료 |',
        ):
            self.assertTrue(_quantitative_consistency_issues('achievement', row, []))

    def test_toc_uses_actual_ordered_pages_and_rejects_missing(self):
        pages = [{'page_number': i + 1, 'text': ''} for i in range(28)]
        for i, (_, title) in enumerate(DESTINATIONS):
            pages[i+2]['text'] = title
        payload = {'page_count': 28, 'page_texts': pages}
        mapping = rhwp_page_map(payload)
        self.assertEqual(mapping['grade_page'], '3')
        self.assertEqual(mapping['summary_ko_page'], '5')
        self.assertEqual(mapping['feedback_lessons_page'], '28')
        pages[-1]['text'] = ''
        with self.assertRaises(ValueError):
            rhwp_page_map(payload)
