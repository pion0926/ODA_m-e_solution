import json
import unittest
from unittest.mock import patch

from backend.oda_me.reports.context import structured_slots_to_json
from kodame_intake.report_generator import (
    _finalize_generated_section_content, _narrative_reader_content,
    _validate_reader_content, QUALITY_TARGETS,
)
from report_outline import canonical_narrative_outline_text, narrative_outline_issues


class NarrativeSlotGateTests(unittest.TestCase):
    part = 'eval-purpose'
    scope = {'project_status': 'ongoing', 'commissioning_agency': '한국연구재단'}

    def validate(self, content):
        with patch.dict(QUALITY_TARGETS, {self.part: (0, 10000)}):
            return _validate_reader_content(self.part, content, '우즈베키스탄', self.scope)

    def test_structured_response_passes_generation_and_export_outline_checks(self):
        body = 'ㅇ 평가 대상\n- (검토 범위) 등록 문헌에 근거하여 실적과 한계를 점검함.'
        source = structured_slots_to_json(self.part, {'evaluation_purpose_scope_body': body})
        final = _finalize_generated_section_content(self.part, source, self.scope)
        self.assertEqual(json.loads(final)['schema'], 'section9_eval_purpose_slots_v1')
        self.assertEqual(self.validate(final), [])
        visible = _narrative_reader_content(self.part, final)
        self.assertIn('등록 문헌에 근거하여 실적과 한계를 점검함.', visible)
        self.assertEqual(narrative_outline_issues(self.part, visible), [])
        ready = canonical_narrative_outline_text(self.part, visible)
        self.assertEqual(self.validate(ready), [])
        self.assertNotIn('evaluation_purpose_scope_body', ready)

    def test_prose_checks_still_reject_unverified_fieldwork_inside_slot(self):
        source = structured_slots_to_json(self.part, {
            'evaluation_purpose_scope_body': 'ㅇ 평가 범위\n- (조사) 현장 조사를 실시함.'})
        self.assertTrue(any('현장조사' in issue for issue in self.validate(source)))

    def test_invalid_envelopes_cannot_hide_bad_prose(self):
        valid = structured_slots_to_json(self.part, {'evaluation_purpose_scope_body': '본문임.'})
        invalid = [valid[:-2], valid.replace('section9_eval_purpose_slots_v1', 'wrong'),
                   json.dumps({'slots': {'evaluation_purpose_scope_body': ['본문임.']}}),
                   json.dumps({'slots': {'evaluation_purpose_scope_body': '본문임.', 'extra': '본문임.'}})]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(_narrative_reader_content(self.part, value), value)
                self.assertTrue(self.validate(value))

    def test_plain_text_remains_supported(self):
        body = 'ㅇ 평가 대상\n- (범위) 등록 문헌의 실적을 확인함.'
        self.assertEqual(_narrative_reader_content(self.part, body), body)
        self.assertEqual(self.validate(body), [])

    def test_explicitly_unperformed_fieldwork_is_a_limitation_not_a_claim(self):
        body = ('ㅇ 검토 한계\n- (수행범위) 현장 조사를 실시하지 않았음. '
                '대면 면담을 수행하지 않았으므로 문헌 검토 범위로 판단을 제한함.')
        self.assertEqual(self.validate(body), [])
        affirmative = body.replace('실시하지 않았음', '실시함').replace('수행하지 않았으므로', '수행함. 따라서')
        issues = self.validate(affirmative)
        self.assertTrue(any('현장조사' in issue for issue in issues))
        self.assertTrue(any('면담' in issue for issue in issues))
