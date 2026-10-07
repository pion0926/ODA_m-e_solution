import unittest
from kodame_intake.pdm_mapping_policy import decision, manual_overrides, qualifies


class PurposeMappingTests(unittest.TestCase):
    def evidence(self, **changes):
        return dict(indicator_id='i', evidence_kind='direct_record', subject_match=True,
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
        old['evidence_matches']['version']=3
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
