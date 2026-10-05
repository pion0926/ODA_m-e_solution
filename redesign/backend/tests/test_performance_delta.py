import unittest
from kodame_intake.performance_delta import reconcile, fingerprint, history
from kodame_intake.performance_review import validate_selection


def observation(value,period='',kind='actual'):
    return {'kind':kind,'value':value,'period':period,'document_id':'a','indicator_id':'i','quote':'source'}


class DeltaTests(unittest.TestCase):
    def test_unreviewed_legacy_empty_pairs_are_rechecked_but_valid_pairs_remain(self):
        from kodame_intake.pdm_evidence import MEASUREMENT_VERSION
        records={'old_empty':{'observations':[]},'measured':{'observations':[observation('6명')]},
                 'reviewed_empty':{'observations':[],'measurement_version':MEASUREMENT_VERSION,'reviews':[{'status':'no_measurement','reason':'범위 불일치'}]}}
        for record in records.values(): record['document_id'] = 'a'
        previous={'source_document_id':'p','model':{'monitoring':{'pair_results':records}}}
        self.assertEqual(set(history(previous,[{'id':'a'}],[],'p')),{'measured','reviewed_empty'})
        self.assertEqual(history(previous,[],[],'p'),{})

    def test_empty_measurement_does_not_claim_extraction(self):
        item={'target':'-','actual':'-'}
        reconcile(item,[],[])
        self.assertEqual(item['measurement_status'],'no_measurement')
    def test_newer_period_wins_even_when_lower(self):
        item={'target':'100명','actual':'80명'}
        reconcile(item,[observation('80명','2024'),observation('60명','2025')],[])
        self.assertEqual(item['actual'],'60명'); self.assertEqual(item['achievement_rate'],60)

    def test_same_date_higher_and_undated_higher(self):
        for period in ('2025-01-01',''):
            item={'target':'100명'}
            reconcile(item,[observation('20명',period),observation('70명',period)],[])
            self.assertEqual(item['actual'],'70명')

    def test_known_date_takes_precedence_over_unknown(self):
        item={'target':'100명'}
        reconcile(item,[observation('90명'),observation('30명','2025')],[])
        self.assertEqual(item['actual'],'30명')
        self.assertTrue(item['measurement_update']['notes'])

    def test_incompatible_units_and_qualitative_conflicts_keep_prior(self):
        for candidates in ([observation('20명','2024'),observation('30건','2025')],
                           [observation('완료','2025'),observation('미완료','2025')]):
            item={'target':'100명','actual':'10명'}
            reconcile(item,candidates,[])
            self.assertEqual(item['actual'],'10명')
            self.assertEqual(item['measurement_status'],'conflict')
            self.assertIsNone(item['achievement_rate'])

    def test_pending_only_selection_retains_old_pairs(self):
        plan={'ready':True,'revision':'rev','message':'','source_document_id':'p','source_file_name':'pdm','input_snapshot':{},
              'documents':[{'id':id,'status':'completed'} for id in ('A','B','C')],
              'indicators':[{'id':'1-1','retained_document_ids':['A'],'analyzed_document_ids':['A']},
                            {'id':'1-2','retained_document_ids':['B'],'analyzed_document_ids':['B']}]}
        result=validate_selection(plan,'rev',{'1-1':['C'],'1-2':['A']})
        self.assertEqual(result['new_mappings'],{'1-1':['C'],'1-2':['A']})
        self.assertEqual(result['mappings'],{'1-1':['A','C'],'1-2':['A','B']})

    def test_fingerprint_is_pair_and_source_specific_not_model_specific(self):
        doc={'id':'a','sha256':'hash'}; indicator={'id':'i','text':'Goal','mov':'Evidence'}
        self.assertNotEqual(fingerprint('p',doc,indicator),fingerprint('p',doc,{**indicator,'id':'j'}))
        self.assertNotEqual(fingerprint('p',doc,indicator),fingerprint('p2',doc,indicator))
