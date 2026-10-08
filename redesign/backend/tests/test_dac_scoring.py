import copy
import unittest

from kodame_intake.dac_scoring import scoring_definition, validate_scoring_trace
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA


class DacScoringTests(unittest.TestCase):
    def setUp(self):
        self.question = EVALUATION_CRITERIA['relevance']['questions'][0]
        self.refs = {'D001': 'document-1'}
        self.payload = {'question_id': self.question['id'], 'score': 3, 'scoring_trace': {
            'selected_level_reason': '등록된 자료의 수요 조사와 정책 대응 내역을 확인하였으나 추가 참여 근거가 부족함.',
            'next_level_gap': '현지 참여를 통해 설계가 변경된 근거를 추가 확인해야 함.',
            'checks': [{'check_id': item['id'], 'status': 'partial', 'finding': '등록 자료에서 실행 계획은 확인하였으나 실제 이행 여부는 추가 검증이 필요함.', 'evidence_document_refs': ['D001']}
                       for item in scoring_definition(self.question)['checks']]}}

    def test_all_eleven_questions_have_distinct_operational_checks(self):
        checks = []
        for criterion in EVALUATION_CRITERIA.values():
            for question in criterion['questions']:
                rule = scoring_definition(question)
                self.assertEqual(len(rule['checks']), 3)
                self.assertEqual(set(rule['levels']), {1, 2, 3, 4})
                checks.extend(check['id'] for check in rule['checks'])
        self.assertEqual(len(checks), 33)
        self.assertEqual(len(set(checks)), 33)

    def test_trace_is_versioned_and_attaches_valid_source_ids(self):
        trace = validate_scoring_trace(self.question, self.payload, self.refs)
        self.assertEqual(trace['selected_score'], 3)
        self.assertEqual(trace['status'], 'assessed')
        self.assertTrue(trace['version'])
        self.assertEqual(trace['checks'][0]['evidence_document_ids'], ['document-1'])

    def test_unknown_evidence_is_not_a_failed_outcome(self):
        self.payload['scoring_trace']['checks'][0].update(status='unverified', evidence_document_refs=[])
        trace = validate_scoring_trace(self.question, self.payload, self.refs)
        self.assertEqual(trace['status'], 'provisional')
        self.assertEqual(trace['selected_score'], 3)

    def test_invalid_output_is_not_silently_clamped_or_fabricated(self):
        cases = []
        for score in (0, 5, '3', 2.5, True):
            case = copy.deepcopy(self.payload); case['score'] = score; cases.append(case)
        case = copy.deepcopy(self.payload); case['question_id'] = 'wrong'; cases.append(case)
        case = copy.deepcopy(self.payload); case.pop('scoring_trace'); cases.append(case)
        case = copy.deepcopy(self.payload); case['score'] = 4; cases.append(case)
        case = copy.deepcopy(self.payload); case['scoring_trace']['checks'][0]['evidence_document_refs'] = ['D999']; cases.append(case)
        case = copy.deepcopy(self.payload); case['scoring_trace']['checks'][0]['evidence_document_refs'] = []; cases.append(case)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_scoring_trace(self.question, case, self.refs)
