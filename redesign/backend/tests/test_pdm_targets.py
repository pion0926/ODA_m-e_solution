import unittest
from kodame_intake.pdm_targets import explicit_target, apply_pdm_targets


class TargetTests(unittest.TestCase):
    def test_target_without_any_mapped_evidence(self):
        from kodame_intake.pdm_monitoring import _monitoring_indicators_from_pdm
        rows = _monitoring_indicators_from_pdm([{'id': 'impact', 'name': '영향', 'indicators': [
            {'id': 'impact-2', 'code': '2', 'text': 'SBA 출산율 (’15 39%, ’18 54%)', 'mov': '조사'}]}], [], [])
        self.assertEqual(rows[0]['target'], '54%')
        self.assertEqual(rows[0]['actual'], '-')
        self.assertIsNone(rows[0]['achievement_rate'])

    def test_preserved_pdm_targets(self):
        cases = {
            'SBA 출산율 15% 증가 (’15 39%, ’18 54%)': '54%',
            '백신 접종률 (2015 96%, 2018 98%)': '98%',
            '견학 참가자 수 (’18년까지 30명 참가)': '30명',
            '신규 조산사 수 (’18년까지 12명 양성)': '12명',
            '이동검진 (’18년까지 324회 실시)': '324회',
            '사회감사 (’18년까지 3회 실시)': '3회',
            '캠페인 (’18년까지 5,000명 참가)': '5,000명',
            'HMIS (’18년까지 25% 기관 정기보고 실시)': '25%',
            '병동 재건축 (종료 전까지 신축건물 2동 준공)': '2동',
        }
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(explicit_target(text)['value'], value)

    def test_no_invented_or_composite_target(self):
        for text in ['강사 수 (명)', '사망률 감소', '외래 10% 증가 (’15 48000건?, ’18 00%)',
                     'ARI (’15 62%, ’18 72%) 설사 (’15 n.a., ’18 n.a.)',
                     '2018년까지 30명 교육 및 2회 훈련', '목표: 30명?',
                     'A (’15 30%, ’18 40%) B (’15 20%, ’18 50%)']:
            with self.subTest(text=text):
                self.assertIsNone(explicit_target(text))

    def test_pdm_overrides_reported_target_and_retains_evidence(self):
        item = {'id': 'a', 'indicator': '산전진찰 (’15 18%, ’18 38%)',
                'target': '60%', 'actual': '37.7%', 'measurement_status': 'extracted',
                'measurement_sources': [{'kind': 'target', 'value': '60%', 'quote': '보고 목표 60%'}]}
        self.assertEqual(apply_pdm_targets([item], 'pdm'), {'a'})
        self.assertEqual(item['target'], '38%')
        self.assertEqual(item['achievement_rate'], 99.2)
        self.assertEqual(item['reported_target_differences'][0]['value'], '60%')
        self.assertEqual(item['selected_measurements']['target']['document_id'], 'pdm')

    def test_unit_mismatch_and_incomplete_remain_unrated(self):
        for status in ['extracted', 'incomplete']:
            item = {'id': 'a', 'indicator': 'HMIS (’18년까지 25% 기관 보고)',
                    'actual': '26건', 'target': '26', 'measurement_status': status}
            apply_pdm_targets([item], 'pdm')
            self.assertEqual(item['target'], '25%')
            self.assertIsNone(item['achievement_rate'])
