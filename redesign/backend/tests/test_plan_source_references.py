import unittest
from unittest.mock import patch
from kodame_intake.document_classification import classify_content
from kodame_intake.openrouter import AnalysisError


def answer(source='S0001', plan=True):
    return {'document_type':'사업계획서','is_project_plan':plan,'reason':'사업 배경과 활동계획',
            'role_confidence':0.95,'role_source_id':source if plan else '',
            'slot_matches':[{'slot_id':'relevance-pcp','confidence':0.9,'reason':'계획 근거','evidence_source_id':source}] if plan else []}


class PlanSourceReferenceTests(unittest.TestCase):
    def test_plan_schema_never_extracts_pdm_or_retypes_quotes(self):
        source = '사 업 계 획 서\n5차년도 항목 (비목)별 예산 산출 내역\n① 교육·장비 예산'
        with patch('kodame_intake.openrouter._request_json',return_value=(answer(),'test')) as request:
            result = classify_content(source,upload_role='project_plan')
        props = request.call_args.kwargs['response_schema']['properties']
        self.assertNotIn('slots',props)
        self.assertNotIn('is_pdm_source',props)
        self.assertNotIn('role_quote',props)
        match = props['slot_matches']['items']['properties']
        self.assertNotIn('evidence_quote',match)
        self.assertNotIn('effectiveness-pdm',match['slot_id']['enum'])
        self.assertEqual(result['role_quotes'],[source])
        self.assertEqual(result['slot_matches'][0]['evidence_quote'],source)
        self.assertFalse(result['is_pdm_source'])
        self.assertTrue(result['is_project_plan'])
        self.assertTrue(all(not value for value in result['slots'].values()))

    def test_unknown_reference_is_retried_then_rejected_with_correct_label(self):
        with patch('kodame_intake.openrouter._request_json',return_value=(answer('S9999'),'test')) as request:
            with self.assertRaisesRegex(AnalysisError,'사업계획서 근거 검증 실패'):
                classify_content('실제 사업계획서',upload_role='project_plan')
        self.assertEqual(request.call_count,3)

    def test_invalid_reference_can_recover_without_inventing_text(self):
        with patch('kodame_intake.openrouter._request_json',side_effect=[(answer('S9999'),'test'),(answer(),'test')]):
            result = classify_content('검증 가능한 사업계획서 원문',upload_role='project_plan')
        self.assertEqual(result['role_quotes'],['검증 가능한 사업계획서 원문'])

    def test_appendix_does_not_have_to_claim_plan_role(self):
        source = '가' * 60000 + '나' * 10000
        with patch('kodame_intake.openrouter._request_json',side_effect=[(answer(),'test'),(answer(plan=False),'test')]) as request:
            result = classify_content(source,upload_role='project_plan')
        self.assertEqual(request.call_count,2)
        self.assertTrue(result['is_project_plan'])
        self.assertFalse(result['is_pdm_source'])

    def test_wrong_document_stays_not_a_plan(self):
        with patch('kodame_intake.openrouter._request_json',return_value=(answer(plan=False),'test')):
            result = classify_content('회의 참석자 명단',upload_role='project_plan')
        self.assertFalse(result['is_project_plan'])
