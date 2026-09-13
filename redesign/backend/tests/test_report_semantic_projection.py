import unittest
from kodame_intake.report_exporter import _narrative_body_probes, _coverage_text


class SemanticProjectionTests(unittest.TestCase):
    def test_achievement_records_are_verified_as_cells_not_literal_body(self):
        body = '- 본 섹션의 설계 기준은 최신 PDM 문서임.\n- [1.2-1] 성과지표: 장비 / 기초선: 미기재 / 목표치: 미기재 / 비고: 확인함.\nㅇ 성과 달성도의 구조적 특징과 한계\n- 새로운 자료를 확보하여 검증할 필요가 있음.'
        probes = _narrative_body_probes('achievement', body)
        self.assertEqual(len(probes), 2)
        self.assertTrue(all('성과지표장비' not in probe for probe in probes))
        self.assertIn(_coverage_text('성과 달성도의 구조적 특징과 한계'), probes[1])

    def test_other_section_body_is_not_filtered(self):
        body = '- [1.2-1] 성과지표: 해당 원문을 공지에서 설명하는 문장임.'
        self.assertIn('성과지표', _narrative_body_probes('notice', body)[0])
