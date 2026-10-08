import unittest
from unittest.mock import patch

from kodame_intake.document_classification import classify_content, is_project_plan, pdm_slots
from kodame_intake.openrouter import analyze_document, AnalysisError


class FoundationAnalysisTests(unittest.TestCase):
    def test_invalid_dac_suggestion_is_omitted_without_retry(self):
        result = {'document_type':'보고서','slot_matches':[
            {'slot_id':'effectiveness-results','evidence_quote':'잘못된 인용','confidence':.9,'reason':'추정'},
            {'slot_id':'efficiency-budget','evidence_quote':'등록 문서 원문','confidence':.9,'reason':'확인'},
        ]}
        with patch('kodame_intake.openrouter._request_json', return_value=(result,'test')) as request:
            actual = classify_content('등록 문서 원문',upload_role='evidence')
        self.assertEqual([m['slot_id'] for m in actual['slot_matches']], ['efficiency-budget'])
        self.assertEqual(request.call_count, 1)

    def test_report_suggestion_without_source_does_not_drop_summary(self):
        from kodame_intake.taxonomy import SECTION_BY_ID
        sid = next(iter(SECTION_BY_ID))
        with patch('kodame_intake.openrouter._request_json', return_value=({'summary':'보존할 요약','section_matches':[{'section_id':sid,'confidence':.9,'evidence_quote':'없는 근거'}, {'section_id':sid,'confidence':.8,'evidence_quote':'원문'}]},'test')), patch('kodame_intake.document_classification.classify_content',return_value={'document_type':'보고서','slot_matches':[]}):
            actual = analyze_document('문서.pdf','원문',upload_role='evidence')
        self.assertEqual(actual['summary'],'보존할 요약')
        self.assertEqual([m['evidence_quote'] for m in actual['section_matches']],['원문'])

    def test_evidence_schema_does_not_request_foundation_detection(self):
        result = {'document_type': '보고서', 'slot_matches': []}
        with patch('kodame_intake.openrouter._request_json', return_value=(result, 'test')) as request:
            actual = classify_content('일반 실적자료', upload_role='evidence')
        properties = request.call_args.kwargs['response_schema']['properties']
        self.assertEqual(set(properties), {'document_type', 'slot_matches'})
        allowed = properties['slot_matches']['items']['properties']['slot_id']['enum']
        self.assertNotIn('effectiveness-pdm', allowed)
        self.assertFalse(actual['is_pdm_source'])
        self.assertFalse(actual['is_project_plan'])

    def test_unclassified_document_cannot_be_remapped_by_bare_dac_labels(self):
        with patch('kodame_intake.openrouter._request_json', return_value=({'summary':'요약','dac_criteria':['effectiveness'],'section_matches':None},'test')), patch('kodame_intake.document_classification.classify_content',return_value={'document_type':'보고서','slot_matches':[]}):
            actual = analyze_document('문서.pdf','원문',upload_role='evidence')
        self.assertEqual(actual['dac_criteria'],[])
        self.assertEqual(actual['section_matches'],[])
        self.assertEqual(actual['summary'],'요약')

    def test_explicit_role_overrides_embedded_plan_pdm(self):
        classification = {'version': 'content-roles-v1', 'is_project_plan': True,
                          'is_pdm_source': True, 'slots': {'outcome_indicator': '80%'}}
        plan = {'upload_role': 'project_plan', 'content_classification': classification}
        pdm = {'upload_role': 'pdm', 'content_classification': classification}
        evidence = {'upload_role': 'evidence', 'content_classification': classification}
        self.assertTrue(is_project_plan(plan))
        self.assertFalse(pdm_slots(plan))
        self.assertTrue(pdm_slots(pdm))
        self.assertFalse(is_project_plan(pdm))
        self.assertFalse(pdm_slots(evidence))
        self.assertFalse(is_project_plan(evidence))

    def test_wrong_foundation_document_fails_validation(self):
        for role in ('project_plan', 'pdm'):
            with self.subTest(role=role), patch('kodame_intake.openrouter._request_json', return_value=({}, 'test')), \
                 patch('kodame_intake.document_classification.classify_content', return_value={'document_type': '보고서'}):
                with self.assertRaises(AnalysisError):
                    analyze_document('file.txt', '본문', upload_role=role)
