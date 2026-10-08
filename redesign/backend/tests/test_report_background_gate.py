import json
import unittest

from backend.oda_me.reports.context import STRUCTURED_SECTION_SLOT_KEYS, structured_slots_to_json
from kodame_intake.report_generator import _validate_reader_content


class BackgroundAgencyGateTests(unittest.TestCase):
    def setUp(self):
        self.slots = dict.fromkeys(STRUCTURED_SECTION_SLOT_KEYS['project-background'], '(사업 배경) 현지 응급의료 교육 수요와 전문인력 양성 필요성을 검토함. ' * 12)

    def blocked(self, content, agency='한국연구재단'):
        return any('KOICA' in issue for issue in _validate_reader_content(
            'project-background', content, '우즈베키스탄', {'commissioning_agency': agency, 'project_status': 'ongoing'}))

    def test_contract_key_is_not_a_factual_claim(self):
        self.assertFalse(self.blocked(structured_slots_to_json('project-background', self.slots)))

    def test_unsupported_agency_in_any_value_remains_blocked(self):
        for key in self.slots:
            for agency in ['KOICA', '코이카']:
                with self.subTest(key=key, agency=agency):
                    slots = {**self.slots, key: agency + ' 지원사업으로 추진됨.'}
                    self.assertTrue(self.blocked(structured_slots_to_json('project-background', slots)))

    def test_verified_agency_is_allowed(self):
        self.slots['koica_policy_alignment'] = 'KOICA 지원사업으로 추진됨.'
        self.assertFalse(self.blocked(structured_slots_to_json('project-background', self.slots), 'KOICA'))

    def test_invalid_structure_does_not_bypass_check(self):
        valid = structured_slots_to_json('project-background', self.slots)
        candidates = [valid[:-2], valid.replace('section6_project_background_slots_v1', 'wrong_schema'),
                      json.dumps({'slots': {**self.slots, 'extra': 'value'}}),
                      json.dumps({'slots': {**self.slots, 'target_region_need': ['KOICA']}}),
                      'KOICA 지원사업으로 추진됨.']
        for content in candidates:
            with self.subTest(content=content[:80]):
                self.assertTrue(self.blocked(content))


if __name__ == '__main__':
    unittest.main()
