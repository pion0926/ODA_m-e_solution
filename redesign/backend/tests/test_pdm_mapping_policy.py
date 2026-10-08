import unittest
from kodame_intake.pdm_mapping_policy import VERSION, decision, manual_overrides, qualifies


class PurposeMappingTests(unittest.TestCase):
    def evidence(self, **changes):
        return dict(indicator_id='i', evidence_kind='direct_record', measurement_relation='observed_result', subject_match=True,
                    activity_match=True, scope_match=True, proves='합동 훈련 실시 기록',
                    evidence_quote='6월 3일 합동 모의훈련을 실시했다.', confidence=.9, **changes)

    def test_individual_record_requires_no_total_number(self):
        self.assertTrue(qualifies(self.evidence()))

    def test_topic_plan_and_unknown_scope_are_not_evidence(self):
        for changes in ({'evidence_kind':'background'}, {'evidence_kind':'target_reference'},
                        {'scope_match':False}, {'activity_match':False}, {'subject_match':False}):
            item=self.evidence(); item.update(changes)
            self.assertFalse(qualifies(item))

    def test_fact_ids_or_old_mapping_cannot_bypass_policy(self):
        old={'evidence_matches':{'version':2,'sources':{'pdm':{'id':'p'}},'pdm':[self.evidence()]}}
        self.assertIsNone(decision({'analysis':old},'i','p'))
        old['evidence_matches']['version']=VERSION
        self.assertIsNotNone(decision({'analysis':old},'i','p'))
        self.assertIsNone(decision({'analysis':old},'i','other'))

    def test_legacy_bulk_confirmation_is_not_manual_addition(self):
        a={'evidence_matches':{'pdm':[{'indicator_id':'automatic'}]},
           'pdm_mapping_overrides':{'source_document_id':'p','included':['automatic','manual'],'excluded':['removed']}}
        self.assertEqual(manual_overrides(a,'p'),({'manual'},{'removed'}))

    def test_versioned_explicit_addition_and_removal(self):
        a={'pdm_mapping_overrides':{'version':3,'source_document_id':'p','included':['i'],'excluded':[]}}
        self.assertEqual(decision({'analysis':a},'i','p')['mapping_origin'],'manual')
        a['pdm_mapping_overrides']['excluded']=['i']
        self.assertIsNone(decision({'analysis':a},'i','p'))

    def test_reported_result_can_map_with_original_ledger_missing(self):
        item = self.evidence()
        item.update(measurement_relation='reported_result', proves='사업 CPCR 강사 양성 실적 6명 보고',
                    limitations='수료명단에 대한 자체 보고이며 자격증 대장 원본은 미첨부')
        self.assertTrue(qualifies(item))

    def test_prerequisite_is_not_a_measurement_even_with_high_topic_confidence(self):
        item = self.evidence()
        item.update(measurement_relation='prerequisite', proves='교원 연수 완료; 단독 운영 과목 비율은 미보고')
        self.assertFalse(qualifies(item))

    def test_v3_manual_choices_survive_version_upgrade_even_when_previously_automatic(self):
        a = {'evidence_matches': {'pdm': [{'indicator_id':'i'}]},
             'pdm_mapping_overrides': {'version':3, 'source_document_id':'p', 'included':['i'], 'excluded':[]}}
        self.assertEqual(manual_overrides(a, 'p'), ({'i'}, set()))
