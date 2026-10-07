import copy
import unittest
from unittest.mock import patch

from kodame_intake.evidence_matching import match_foundations
from kodame_intake.openrouter import AnalysisError


class EvidenceMatchingTests(unittest.TestCase):
    def setUp(self):
        self.context = {'sources': {'project_plan': {'id': 'plan'}, 'pdm': {'id': 'pdm'}},
                        'plan_text': '교원 역량 강화 사업을 추진한다.',
                        'indicators': [{'id': 'outcome-1', 'tier': 'outcome', 'text': '교원 수료율 80%', 'mov': '수료 명단'}]}
        self.plan = {'topic': '교원 역량 강화', 'confidence': .9, 'rationale': '연수 활동 관련',
                     'evidence_quote': '교원 연수를 실시했다.', 'reference_quote': '교원 역량 강화 사업'}
        self.pdm = {'indicator_id': 'outcome-1', 'confidence': .9, 'rationale': '수료 증빙', 'evidence_quote': '교원 연수를 실시했다.'}
        self.pdm.update(evidence_kind='calculation_input',measurement_relation='calculation_component',proves='교원 연수 이행 기록',limitations='전체 수료율은 명단 대조 필요',subject_match=True,activity_match=True,scope_match=True)

    def match(self, result, text='교원 연수를 실시했다.'):
        with patch('kodame_intake.evidence_matching._request_json', return_value=(copy.deepcopy(result), 'test')):
            return match_foundations(text, context=self.context)

    def test_plan_match_does_not_imply_pdm_match(self):
        result = self.match({'project_plan': [self.plan], 'pdm': []})
        self.assertEqual(len(result['project_plan']), 1)
        self.assertEqual(result['pdm'], [])
        self.assertEqual(result['sources'], self.context['sources'])

    def test_pdm_match_does_not_require_plan_match(self):
        result = self.match({'project_plan': [], 'pdm': [self.pdm]})
        self.assertEqual(result['project_plan'], [])
        self.assertEqual(result['pdm'][0]['tier'], 'outcome')
        self.assertEqual(result['pdm'][0]['indicator'], '교원 수료율 80%')
        self.assertNotIn('achievement_rate', result['pdm'][0])

    def test_no_match_is_valid(self):
        self.assertEqual(self.match({'project_plan': [], 'pdm': []})['pdm'], [])

    def test_reported_measurement_is_saved_but_prerequisite_is_reference_only(self):
        reported = {**self.pdm, 'measurement_relation':'reported_result', 'limitations':'자체 보고, 원 명부 미대조'}
        result = self.match({'project_plan':[], 'pdm':[reported]})
        self.assertEqual(result['pdm'][0]['limitations'], reported['limitations'])
        prerequisite = {**self.pdm, 'measurement_relation':'prerequisite'}
        result = self.match({'project_plan':[], 'pdm':[prerequisite]})
        self.assertEqual(result['pdm'], [])
        self.assertEqual(len(result['pdm_references']), 1)

    def test_invented_plan_or_evidence_quote_rejected(self):
        for key in ('reference_quote', 'evidence_quote'):
            with self.subTest(key=key):
                result = self.match({'project_plan': [{**self.plan, key: '본문에 없는 내용'}], 'pdm': [self.pdm]})
                self.assertEqual(result['project_plan'], [])
                self.assertEqual(len(result['pdm']), 1)

    def test_unknown_pdm_id_rejected(self):
        result = self.match({'project_plan': [self.plan], 'pdm': [{**self.pdm, 'indicator_id': 'invented'}]})
        self.assertEqual(result['pdm'], [])
        self.assertEqual(len(result['project_plan']), 1)

    def test_unverified_suggestions_do_not_trigger_retry(self):
        with patch('kodame_intake.evidence_matching._request_json', return_value=({'project_plan': [], 'pdm': [{**self.pdm, 'evidence_quote':'잘못된 인용'}]}, 'test')) as request:
            result = match_foundations('원문', context=self.context)
        self.assertEqual(result['pdm'], [])
        self.assertEqual(request.call_count, 1)

    def test_actual_ai_failure_is_not_reported_as_successful_registration(self):
        with patch('kodame_intake.evidence_matching._request_json',side_effect=AnalysisError('AI JSON generation failed')):
            with self.assertRaises(AnalysisError):
                match_foundations('원문',context=self.context)

    def test_overlap_deduplicates_indicator_and_filters_low_confidence(self):
        result = self.match({'project_plan': [{**self.plan, 'confidence': .2}], 'pdm': [self.pdm]},
                            '교원 연수를 실시했다.' + 'x' * 27980 + '교원 연수를 실시했다.')
        self.assertEqual(result['project_plan'], [])
        self.assertEqual(len(result['pdm']), 1)
