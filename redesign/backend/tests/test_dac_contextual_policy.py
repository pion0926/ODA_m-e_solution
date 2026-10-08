import unittest
from tests import test_dac_rules as fixtures
from kodame_intake.dac_rules import score_question, mean_score, RULES
from kodame_intake.dac_schema import question_schema


class ContextualPolicyTests(unittest.TestCase):
    def test_two_observed_outcome_checks_score_two_despite_40_percent_coverage(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture('effectiveness-q2',state='limited')
        for index in (0,2,3):item['indicators'][index]['state']='unverified'
        result=score_question('effectiveness-q2',item,evidence)
        self.assertEqual(result['coverage'],.4)
        self.assertEqual(result['merit_index'],50)
        self.assertEqual(result['base_score'],2)
        self.assertEqual(result['selected_score'],2)
        self.assertEqual(result['status'],'proposed')
        self.assertEqual(result['evidence_status'],'needs_evidence')
        self.assertEqual(result['timing']['scored_count'],2)
        self.assertEqual(result['timing']['unverified_count'],3)
        self.assertEqual(mean_score([2,result['selected_score'],2]),2)
        self.assertIn('별도 보완사항',result['selected_level_reason'])
        self.assertTrue(result['next_level_gap'])

    def test_low_confidence_does_not_invent_or_erase_the_observed_score(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='limited')
        for c in item['indicators']:
            c['quality'].update(source_grade=1,directness=.5,recency=0)
        result=score_question('relevance-q1',item,evidence)
        self.assertLess(result['confidence'],50)
        self.assertEqual(result['selected_score'],2)
        self.assertEqual(result['evidence_status'],'needs_evidence')

    def test_sparse_observed_failure_stays_one_with_no_two_point_floor(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='negative')
        for c in item['indicators'][1:]:c['state']='unverified'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],1)
        self.assertEqual(result['coverage'],.2)
        self.assertEqual(result['timing']['scored_count'],1)

    def test_partial_conflict_does_not_hide_confirmed_adverse_facts(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='negative')
        item['indicators'][0]['state']='conflicted'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],1)
        self.assertEqual(result['evidence_status'],'conflicted')
        self.assertEqual(result['timing']['scored_count'],4)

    def test_provisional_score_and_evidence_status_reach_report_context(self):
        from kodame_intake.report_evaluation_context import for_report
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='limited')
        for c in item['indicators'][:3]:c['state']='unverified'
        trace=score_question('relevance-q1',item,evidence)
        result=for_report([{'question_assessments':[{'score':trace['selected_score'],'scoring_trace':trace}]}])
        question=result[0]['question_assessments'][0]
        self.assertEqual(question['score'],2)
        self.assertEqual(question['scoring_trace']['evidence_status'],'needs_evidence')
        self.assertEqual(question['scoring_trace']['confidence'],trace['confidence'])

    def test_partial_execution_is_two_without_blanket_minimum(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='limited')
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],2)
        self.assertEqual(result['merit_index'],50)
        failed,evidence=fixtures.DacRuleEngineTests().fixture(state='negative')
        self.assertEqual(score_question('relevance-q1',failed,evidence)['selected_score'],1)

    def test_previous_39_8_cliff_is_not_a_failure(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='limited')
        item['indicators'][0]['state']='substantial'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],2)
        self.assertEqual(result['merit_index'],55)

    def test_not_due_is_excluded_from_coverage_not_zero(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture()
        for c in item['indicators'][:3]:
            c.update(state='not_due',finding='原문 계획에 따라 해당 목표의 완료 예정일이 아직 도래하지 않았습니다.')
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],3)
        self.assertEqual(result['coverage'],1)
        self.assertEqual(result['timing']['not_due_count'],3)
        self.assertEqual(result['timing']['scored_count'],2)
        for c in item['indicators']:c['state']='not_due'
        self.assertIsNone(score_question('relevance-q1',item,evidence)['selected_score'])

    def test_not_due_requires_evidence(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='not_due')
        item['indicators'][0]['evidence_ids']=[]
        with self.assertRaises(ValueError):score_question('relevance-q1',item,evidence)

    def test_missing_data_never_becomes_two(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='unverified')
        result=score_question('relevance-q1',item,evidence)
        self.assertIsNone(result['selected_score'])
        self.assertEqual(result['timing']['unverified_count'],5)

    def test_merit_is_independent_of_source_grade(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture(state='verified')
        high=score_question('relevance-q1',item,evidence)
        for c in item['indicators']:c['quality']['source_grade']=1
        low=score_question('relevance-q1',item,evidence)
        self.assertEqual(high['merit_index'],low['merit_index'])
        self.assertGreater(high['confidence'],low['confidence'])

    def test_due_quantitative_failure_is_not_floored(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture('effectiveness-q1',state='negative')
        evidence['E1']['quote']+=' 목표 100명 실적 20명.'
        item['indicators'][0]['measurements']=[{'metric':'수료','target':100,'actual':20,'unit':'명','period':'2025','population':'교육생','direction':'higher','comparable':True,'due':True,'target_evidence_ids':['E1'],'actual_evidence_ids':['E1']}]
        result=score_question('effectiveness-q1',item,evidence)
        self.assertEqual(result['selected_score'],1)

    def test_policy_is_versioned_as_internal_adaptation(self):
        self.assertIn('contextual',RULES['version'])
        self.assertIn('공식',RULES['notice'])
        schema=question_schema('relevance-q1',['E1'])
        enum=schema['properties']['question_assessments']['items']['properties']['indicators']['items']['properties']['state']['enum']
        self.assertIn('not_due',enum)
