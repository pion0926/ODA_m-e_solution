import unittest
from kodame_intake.hwpx_layout.achievement_readability import improve_achievement_readability
from kodame_intake.hwpx_layout.tables import achievement_page_groups


class AchievementReadabilityTests(unittest.TestCase):
    def test_numeric_pdm_ids_preserve_fields_and_get_readable_notes(self):
        from backend.oda_me.hwpx.patchers import parse_achievement_items, achievement_item_fields
        record = '- [1.2-1] 성과지표: 장비 / 기초선: 미기재 / 목표치: 미기재 / 종료선 또는 현재 실적: 미기재 / 대비 결과: 산출 불가 / 지표입증수단(MOV): 검수조서 / 비고: 사용기록 확인이 필요함.'
        rows = parse_achievement_items(record)
        self.assertEqual(len(rows), 1)
        self.assertEqual(achievement_item_fields(rows[0], 0)['indicator'], '장비')
        paragraph = f'<hp:p id="10" paraPrIDRef="92" pageBreak="0"><hp:run charPrIDRef="28"><hp:t>{record}</hp:t></hp:run></hp:p>'
        result, count = improve_achievement_readability(paragraph)
        self.assertEqual(count, 1)
        self.assertIn('지표의 주요 진척과 확인 과제', result)
        self.assertIn('- 사용기록 확인이 필요함.', result)
        self.assertNotIn('기초선:', result)
        self.assertIn('id="2147483648" paraPrIDRef="69" pageBreak="1"', result)
        self.assertIn('id="10" paraPrIDRef="92" pageBreak="0"', result)

    def test_first_page_reserves_title_space(self):
        groups = achievement_page_groups(12)
        self.assertEqual([len(g) for g in groups], [4,5,3])
        self.assertEqual([i for g in groups for i in g], list(range(12)))

    def test_records_become_grouped_notes_without_touching_table(self):
        record = '- [outcome-1-1] 명칭: 성과지표: 교육 / 기초선: 0 / 목표치: 10명 / 종료선 또는 현재 실적: 6명 / 대비 결과: 진행 / 지표입증수단(MOV): 명부 / 비고: 후속 확인이 필요함.'
        paragraph = f'<hp:p paraPrIDRef="71"><hp:run charPrIDRef="28"><hp:t>{record}</hp:t></hp:run></hp:p>'
        table = '<hp:tbl><hp:tc>' + paragraph + '</hp:tc></hp:tbl>'
        fixed, count = improve_achievement_readability(table + paragraph)
        self.assertIn(table, fixed)
        self.assertEqual(count, 1)
        self.assertIn('성과(Outcome)의 주요 진척과 확인 과제', fixed)
        self.assertIn('- 후속 확인이 필요함.', fixed)
        self.assertNotIn('[outcome-', fixed[len(table):])
        self.assertEqual(improve_achievement_readability(fixed), (fixed, 0))
