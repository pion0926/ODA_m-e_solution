import json
import unittest

from backend.oda_me.reports.context import STRUCTURED_SECTION_SLOT_KEYS, STRUCTURED_SECTION_SCHEMAS
from kodame_intake.report_response import section_response_content, normalize_achievement_structure
from kodame_intake.report_generator import _ensure_official_grade_statement, _finalize_generated_section_content


class ReportResponseTests(unittest.TestCase):
    def test_achievement_labels_accept_pdm_case_and_spacing(self):
        for label in ['outcome-1-1', 'Outcome 1-1', 'Outputs 1.1-1', '1-1', '1.2-1']:
            body = f'- [{label}] 지표 원문\n- 세부 근거\n\nㅇ 종합적 진단\n- 시사점 원문'
            result = normalize_achievement_structure(body)
            self.assertIn('3. 종합 평가 및 시사점\n\nㅇ 종합적 진단', result)
            self.assertNotIn('####', result)
            self.assertEqual(result.replace('3. 종합 평가 및 시사점\n\n', ''), body)
            self.assertEqual(normalize_achievement_structure(result), result)

    def test_plain_text_response(self):
        self.assertEqual(section_response_content({'content': ' 본문 '}, 'conclusion'), '본문')
        self.assertEqual(section_response_content({'revised_content': '교정'}, 'conclusion', 'revised_content'), '교정')

    def test_all_slot_envelopes_preserve_schema_and_keys(self):
        for part, keys in STRUCTURED_SECTION_SLOT_KEYS.items():
            document = {'schema': STRUCTURED_SECTION_SCHEMAS[part], 'slots': dict.fromkeys(keys, '검증된 근거임.')}
            for payload, field in [(document, 'content'), ({'content': document}, 'content'), ({'revised_content': document}, 'revised_content')]:
                with self.subTest(part=part, field=field):
                    content = section_response_content(payload, part, field)
                    final = _finalize_generated_section_content(part, content, {'project_status': 'ongoing'})
                    actual = json.loads(final)
                    self.assertEqual(actual['schema'], document['schema'])
                    self.assertEqual(set(actual['slots']), set(document['slots']))
                    if part == 'eval-purpose':
                        self.assertIn('검증된 근거임.', actual['slots']['evaluation_purpose_scope_body'])
                    else:
                        self.assertEqual(actual, document)

    def test_wrong_schema_or_missing_slots_rejected(self):
        with self.assertRaises(ValueError):
            section_response_content({'schema': 'wrong', 'slots': {'evaluation_purpose_scope_body': '본문'}}, 'eval-purpose')
        with self.assertRaises(ValueError):
            section_response_content({'slots': {'other': '본문'}}, 'eval-purpose')

    def test_appended_grade_statement_is_a_detail_paragraph(self):
        evaluations = [{'criterion_id': key, 'score': 3} for key in ['relevance', 'coherence', 'effectiveness', 'efficiency', 'sustainability']]
        result = _ensure_official_grade_statement('conclusion', 'ㅇ 종합판정\n- 근거임.', evaluations)
        self.assertIn('\n\n- 공식 종합판정', result)
