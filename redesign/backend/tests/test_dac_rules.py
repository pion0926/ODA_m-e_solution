import copy
import unittest
from unittest.mock import patch

from kodame_intake.dac_rules import RULES, definition, score_question, mean_score
from kodame_intake.dac_measurements import calculate
from kodame_intake.dac_rules import refs_for
from kodame_intake.dac_assessor import template, validate, assess_criterion, evidence_registry
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from kodame_intake.dac_replay import fingerprint


class DacRuleEngineTests(unittest.TestCase):
    def test_unexplained_source_family_does_not_create_independence(self):
        item,evidence=self.fixture()
        evidence['E2']={**evidence['E1'],'document_id':'d2','source_sha256':'sha2'}
        c=item['indicators'][0]
        c['evidence_ids']=['E1','E2']
        c['source_families']=[{'name':'A','provenance':'기관 A','evidence_ids':['E1']},
                              {'name':'B','provenance':'기관 B','evidence_ids':['E2']}]
        check=score_question('relevance-q1',item,evidence)['checks'][0]
        self.assertFalse(check['quality']['independent_corroboration'])
        self.assertTrue(any('불충분' in rule for rule in check['applied_rules']))

    def test_data_absence_cannot_be_a_negative_performance_observation(self):
        item,evidence=self.fixture(state='negative')
        for check in item['indicators']:
            check['negative_fact_quote']=''
            check['finding']='분리데이터와 데이터사전이 원문에서 확인되지 않습니다.'
        result=score_question('relevance-q1',item,evidence)
        self.assertIsNone(result['selected_score'])
        self.assertTrue(all(c['state']=='unverified' for c in result['checks']))

    def test_unproven_absence_of_red_flag_is_unknown_not_failure(self):
        item,evidence=self.fixture()
        item['red_flag']['evidence_ids']=[]
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['red_flag']['status'],'unverified')
        self.assertEqual(result['red_flag']['proposed_status'],'not_met')
        self.assertEqual(result['selected_score'],3)
        item['red_flag']['status']='met'
        with self.assertRaises(ValueError):
            score_question('relevance-q1',item,evidence)

    def test_self_report_citation_cannot_be_promoted_to_official_source(self):
        item,evidence=self.fixture(state='verified')
        evidence['E1']['source_grade_ceiling']=1
        result=score_question('relevance-q1',item,evidence)
        self.assertTrue(all(c['quality']['effective_source_grade']==1 for c in result['checks']))
        self.assertTrue(all(c['state']=='verified' for c in result['checks']))
        self.assertLess(result['selected_score'],4)

    def test_each_question_receives_only_its_own_sources_and_schema(self):
        criterion=EVALUATION_CRITERIA['relevance']
        corpus=[{'document_id':'d1','ref':'D001','file_name':'사업계획서.pdf','summary':'요약',
            'fulltext_review':{'status':'completed'},'question_evidence':[
                {'question_id':q['id'],'quote':'계획된 활동과 위험','finding':'계획 단계 내용'} for q in criterion['questions']]}]
        pdm={'status':'unavailable','model':{}}
        calls=[]
        def answer(system,prompt,title,**kwargs):
            import json
            payload=json.loads(prompt.strip())
            qid=payload['questions'][0]['question_id']
            self.assertTrue(all(e['question_id']==qid for e in payload['evidence']))
            self.assertTrue(all(e['source_grade_ceiling']==1 for e in payload['evidence']))
            self.assertIn('response_schema',kwargs)
            calls.append(qid)
            single={**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]}
            raw=template(single)
            q=raw['question_assessments'][0]
            q['finding']='제공된 근거가 계획 단계에 그쳐 실행 성과를 판단할 수 없습니다.'
            return raw,'test'
        with patch('kodame_intake.dac_assessor._request_json',side_effect=answer):
            result=assess_criterion('relevance',criterion,corpus,{},pdm)
        self.assertEqual(calls,[q['id'] for q in criterion['questions']])
        self.assertIsNone(result['score'])

    def test_quantitative_values_attached_to_korean_text_are_grounded(self):
        from kodame_intake.dac_measurements import grounded_number
        self.assertEqual(grounded_number(100,[{'quote':'목표100명, 실적90명'}]),100)
        with self.assertRaises(ValueError):
            grounded_number(10,[{'quote':'목표100명, 실적90명'}])

    def test_missing_quantitative_measurement_cannot_be_fully_verified(self):
        item,evidence=self.fixture('effectiveness-q1',state='verified')
        item['indicators'][0]['quality']['source_grade']=3
        result=score_question('effectiveness-q1',item,evidence)
        self.assertEqual(result['checks'][0]['state'],'substantial')

    def test_rounded_fraction_uses_exact_source_and_ambiguous_rounding_is_rejected(self):
        from decimal import Decimal
        from kodame_intake.dac_measurements import grounded_number
        self.assertEqual(grounded_number(97.33,[{'quote':'실적 97.33333333333%'}]),Decimal('97.33333333333'))
        with self.assertRaises(ValueError):
            grounded_number(97,[{'quote':'실적 97.33333333333%'}])
        with self.assertRaises(ValueError):
            grounded_number(97.33,[{'quote':'2025년 97.331%, 2026년 97.334%'}])

    def test_redaction_preserves_valid_dates_but_hides_identifiers(self):
        from kodame_intake.openrouter import redact_for_external_analysis
        result,_=redact_for_external_analysis('기준일 2025-03-25 전화 010-1234-5678 계좌 123-456-7890')
        self.assertIn('2025-03-25', result)
        self.assertNotIn('010-1234-5678', result)
        self.assertNotIn('123-456-7890', result)

    def test_nullable_score_survives_hwpx_adapter(self):
        from backend.oda_me.hwpx.formatting import criterion_grade_rows, format_score
        context={'criteria':[{'id':'relevance','currentScore4':None,'evaluationResult':{
            'score':None,'summary':'자료보완 필요','questionAssessments':[{'score':None,'finding':'미확인'}]}}]}
        rows=criterion_grade_rows(context)
        self.assertIsNone(rows[0]['score'])
        self.assertIsNone(rows[0]['questionRows'][0]['score'])
        self.assertEqual(format_score(None),'판정보류')

    def fixture(self, qid='relevance-q1', state='substantial'):
        criterion = EVALUATION_CRITERIA[qid.split('-q')[0]]
        item = next(q for q in template(criterion)['question_assessments'] if q['question_id']==qid)
        evidence = {'E1':{'question_id':qid,'document_id':'d1','document_ref':'D001','source_sha256':'sha1',
                           'quote':'2025년 목표 100명 실적 90명 공식 승인 기록. 해당 활동은 실시하지 않았습니다.', 'file_name':'공식기록.pdf'}}
        for c in item['indicators']:
            c.update(state=state, finding='2025년 공식 기록에서 주요 범위의 실행과 일부 미완료를 확인했습니다.',evidence_ids=['E1'])
            c['negative_fact_quote']='해당 활동은 실시하지 않았습니다.' if state=='negative' else ''
            c['quality']={'source_grade':2,'directness':1,'recency':1,'rationale':'해당 기간의 공식 기록으로 실행과 일부 미완료를 확인합니다.'}
        for key in ('four_point_gate','specific_cap','red_flag'):
            item[key]={'status':'not_met','finding':'2025년 공식 기록을 검토하였으며 해당 조건의 발생이 확인되지 않았습니다.','evidence_ids':['E1']}
        return item,evidence

    def test_all_source_indicators_weights_and_level_texts(self):
        self.assertEqual(len(RULES['questions']),11)
        ids=[]
        for q in RULES['questions'].values():
            self.assertEqual(len(q['checks']),5)
            self.assertEqual(sum(c['weight'] for c in q['checks']),100)
            self.assertTrue(all(isinstance(v,str) and len(v)>10 for v in q['official_levels'].values()))
            ids.extend(c['id'] for c in q['checks'])
        self.assertEqual(len(set(ids)),55)

    def test_llm_score_is_never_authoritative(self):
        item,evidence=self.fixture()
        item['score']=4
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],3)
        self.assertEqual(result['merit_index'],75)
        self.assertEqual(result['coverage'],1)
        self.assertEqual(result,score_question('relevance-q1',copy.deepcopy(item),copy.deepcopy(evidence)))

    def test_missing_is_not_negative_and_cannot_produce_a_grade(self):
        item,evidence=self.fixture(state='unverified')
        result=score_question('relevance-q1',item,evidence)
        self.assertIsNone(result['selected_score'])
        self.assertIsNone(result['merit_index'])
        self.assertEqual(result['coverage'],0)
        negative,_=self.fixture(state='negative')
        self.assertEqual(score_question('relevance-q1',negative,evidence)['selected_score'],1)

    def test_coverage_boundary_60_and_40_keep_observed_score(self):
        item,evidence=self.fixture()
        for c in item['indicators'][:2]: c['state']='unverified'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['coverage'],.6)
        self.assertEqual(result['selected_score'],3)
        item['indicators'][2]['state']='unverified'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['selected_score'],3)
        self.assertEqual(result['coverage'],.4)
        self.assertEqual(result['status'],'proposed')
        self.assertEqual(result['evidence_status'],'needs_evidence')

    def test_conflict_is_separate_from_other_observed_performance(self):
        item,evidence=self.fixture()
        item['indicators'][0]['state']='conflicted'
        result=score_question('relevance-q1',item,evidence)
        self.assertEqual(result['coverage'],.8)
        self.assertEqual(result['selected_score'],3)
        self.assertEqual(result['status'],'proposed')
        self.assertEqual(result['evidence_status'],'conflicted')
        self.assertEqual(result['timing']['scored_count'],4)

    def test_four_requires_all_atoms_and_explicit_gate(self):
        item,evidence=self.fixture(state='verified')
        self.assertEqual(score_question('relevance-q1',item,evidence)['selected_score'],3)
        item['four_point_gate']['status']='met'
        self.assertEqual(score_question('relevance-q1',item,evidence)['selected_score'],4)
        item['indicators'][0]['state']='substantial'
        self.assertEqual(score_question('relevance-q1',item,evidence)['selected_score'],3)

    def test_self_report_keeps_merit_but_requires_support_for_top_score(self):
        item,evidence=self.fixture(state='verified')
        item['four_point_gate']['status']='met'
        for c in item['indicators']: c['quality']['source_grade']=1
        r=score_question('relevance-q1',item,evidence)
        self.assertEqual(r['selected_score'],3)
        self.assertTrue(all(c['state']=='verified' for c in r['checks']))
        self.assertEqual(r['merit_index'],100)
        self.assertIn('FOUR_POINT_CONFIDENCE',[cap['rule'] for cap in r['applied_rules']])

    def test_directness_and_period_quality_cannot_be_hidden(self):
        item,evidence=self.fixture()
        for c in item['indicators']:
            c['quality'].update(source_grade=1,directness=0,recency=0)
        r=score_question('relevance-q1',item,evidence)
        self.assertEqual(r['coverage'],0)
        self.assertEqual(r['selected_score'],3)
        self.assertEqual(r['evidence_status'],'needs_evidence')
        self.assertLess(r['confidence'],50)

    def test_specific_cap_and_verified_red_flag(self):
        item,evidence=self.fixture('relevance-q2')
        item['specific_cap']['status']='met'
        self.assertEqual(score_question('relevance-q2',item,evidence)['selected_score'],2)
        item['red_flag']['status']='met'
        self.assertEqual(score_question('relevance-q2',item,evidence)['selected_score'],1)

    def test_foreign_question_and_fabricated_refs_rejected(self):
        item,evidence=self.fixture()
        for bad in ('missing','E2'):
            payload=copy.deepcopy(item); payload['indicators'][0]['evidence_ids']=[bad]
            evidence['E2']={**evidence['E1'],'question_id':'efficiency-q1'}
            with self.assertRaises(ValueError): score_question('relevance-q1',payload,evidence)

    def test_repeated_same_source_does_not_manufacture_corroboration(self):
        item,evidence=self.fixture()
        item['indicators'][0]['source_families']=[{'name':n,'provenance':'독립 출처라고 기술하지만 동일 파일을 반복 인용합니다.','evidence_ids':['E1']} for n in ('A','B')]
        result=score_question('relevance-q1',item,evidence)
        self.assertFalse(result['checks'][0]['quality']['independent_corroboration'])

    def test_decimal_criterion_average_and_null_propagation(self):
        self.assertEqual(mean_score([2,2,3]),2.3)
        self.assertEqual(mean_score([3,4]),3.5)
        self.assertIsNone(mean_score([3,None]))

    def test_server_recomputes_ratio_from_cited_numbers(self):
        item,evidence=self.fixture('effectiveness-q1',state='verified')
        item['four_point_gate']['status']='met'
        item['indicators'][0]['measurements']=[{'metric':'교육','target':100,'actual':90,'unit':'명','period':'2025년',
            'population':'교육대상자','direction':'higher','comparable':True,'due':True,
            'target_evidence_ids':['E1'],'actual_evidence_ids':['E1']}]
        r=score_question('effectiveness-q1',item,evidence)
        self.assertEqual(r['checks'][0]['measurements'][0]['ratio'],.9)
        self.assertEqual(r['checks'][0]['state'],'substantial')
        self.assertEqual(r['selected_score'],3)
        item['indicators'][0]['measurements'][0]['actual']=1000
        result=score_question('effectiveness-q1',item,evidence)
        self.assertEqual(result['checks'][0]['state'],'unverified')
        self.assertIsNone(result['checks'][0]['measurements'][0]['ratio'])
        self.assertIn('확인할 수 없습니다',result['checks'][0]['measurements'][0]['validation_error'])

    def test_snapshot_is_invalidated_by_new_content_not_only_document_count(self):
        with patch('kodame_intake.dac_replay.connection') as connection:
            connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=None
            base=[{'id':'a','sha256':'aaa','summary':'계획'}]
            digest=fingerprint(base,'model')
            self.assertEqual(digest,fingerprint(copy.deepcopy(base),'model'))
            self.assertNotEqual(digest,fingerprint([{**base[0],'sha256':'bbb'}],'model'))
            self.assertNotEqual(digest,fingerprint(base+[{'id':'b','sha256':'new'}],'model'))
            self.assertNotEqual(digest,fingerprint(base,'new-model'))


if __name__=='__main__': unittest.main()
