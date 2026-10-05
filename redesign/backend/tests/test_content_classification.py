import copy
import unittest
from unittest.mock import patch

from kodame_intake.document_classification import VERSION, classify_content, pdm_slots, NoPdmSource
from kodame_intake.document_slots import document_slot_matches
from kodame_intake.pdm_monitoring import _select_pdm_source, _numbered_items
from kodame_intake.pdm_source import PDM_SLOT_KEYS
from kodame_intake.openrouter import AnalysisError


def response(pdm=True, plan=False):
    return {"document_type": "사업계획서" if plan else "PDM" if pdm else "보고서",
            "is_pdm_source": pdm, "is_project_plan": plan, "reason": "사업 설계 본문 확인",
            "role_confidence": 0.95,
            "role_quote": "목표", "slot_matches": [],
            "slots": {key: ["1. 산전검진율 80%"] if key == "outcome_indicator" and pdm else [] for key in PDM_SLOT_KEYS}}


class ContentClassificationTests(unittest.TestCase):
    def test_hwp_wrapped_targets_are_not_extra_indicators(self):
        items = _numbered_items('1.산전진찰 4회 완수율\n(2018년 38%)\n2. 병원 외래진료\n(10% 증가)')
        self.assertEqual(len(items), 2)
        self.assertIn('38%', items[0]['text'])
        self.assertEqual(items[1]['code'], '2')

    def classify(self, result):
        with patch('kodame_intake.openrouter._request_json', return_value=(result, 'test-model')):
            return {"content_classification": classify_content("목표\n1. 산전검진율 80%")}

    def test_all_extensions_and_unnamed_sources(self):
        analysis = self.classify(response())
        for name in ('붙임.hwp', '첨부.hwpx', '사업설계.xlsx', 'document.docx', 'scan.pdf', 'matrix.txt'):
            doc = {'original_name': name, 'analysis': analysis, 'queue_position': 1}
            self.assertEqual(_select_pdm_source([doc])[1]['outcome_indicator'], '1. 산전검진율 80%')
            self.assertEqual(document_slot_matches(name, analysis)[0]['slot_id'], 'effectiveness-pdm')

    def test_pdm_filename_does_not_make_report_a_pdm(self):
        analysis = self.classify(response(False))
        with self.assertRaises(NoPdmSource):
            _select_pdm_source([{'original_name': '최신 PDM.pdf', 'analysis': analysis}])
        self.assertEqual(document_slot_matches('최신 PDM.pdf', analysis), [])

    def test_plan_and_embedded_pdm_keep_both_roles(self):
        analysis = self.classify(response(True, True))
        self.assertEqual(analysis['content_classification']['document_type'], '사업계획서')
        self.assertEqual({m['slot_id'] for m in document_slot_matches('(A-2) 네팔 무구지역.hwp', analysis)},
                         {'relevance-pcp', 'effectiveness-pdm'})

    def test_newest_semantically_classified_source_wins(self):
        analysis = self.classify(response())
        old = {'original_name': '최신 PDM.pdf', 'queue_position': 1, 'analysis': analysis}
        new = {'original_name': '붙임.hwp', 'queue_position': 2, 'analysis': analysis}
        self.assertIs(_select_pdm_source([old, new])[0], new)

    def test_missing_cells_remain_empty(self):
        self.assertEqual(pdm_slots(self.classify(response()))['outcome_mov'], '')

    def test_invented_target_rejected(self):
        result = response()
        result['slots']['outcome_indicator'] = ['1. 산전검진율 100%']
        with self.assertRaises(AnalysisError):
            self.classify(result)

    def test_unquoted_plan_rejected(self):
        result = response(False, True)
        result['role_quote'] = '원문에 없음'
        with self.assertRaises(AnalysisError):
            self.classify(result)

    def test_appendix_after_intake_excerpt_is_analyzed(self):
        text = 'x' * 125000 + '목표\n1. 산전검진율 80%'
        with patch('kodame_intake.openrouter._request_json', side_effect=[
            (response(False), 'test'), (response(False), 'test'), (response(), 'test')]) as request:
            analysis = classify_content(text)
        self.assertTrue(analysis['is_pdm_source'])
        self.assertEqual(request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
