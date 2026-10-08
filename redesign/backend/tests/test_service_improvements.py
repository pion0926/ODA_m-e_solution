import unittest
from unittest.mock import patch
from kodame_intake.foundation_facts import extract_plan_facts
from kodame_intake.source_locations import locate
from kodame_intake.measurement_recheck import suspicious_negatives
from kodame_intake.dac_scope_policy import missing_ranges, escalation_questions
from kodame_intake.report_review_policy import score_or_none, review_schema, claim_audit
from kodame_intake.report_content_policy import evidence_targets
from kodame_intake.evaluation_versions import compare, digest
from kodame_intake.indicator_identity import assign_identities
from kodame_intake.domain_neutral_matching import candidate_match


class ImprovementTests(unittest.TestCase):
    def test_plan_tail_and_rejected_invented_quote(self):
        text='[PDF 페이지 1]\n'+'가나다라 '*4000+'\n[PDF 페이지 2]\n사업 예산은 3억원이다.'
        def response(system,prompt,title,**kwargs):
            import json
            chunk=json.loads(prompt)['text']
            return {'facts':[{'field':'budget','value':'3억원','quote':'사업 예산은 3억원이다.'}] if '3억원' in chunk else
                    [{'field':'country','value':'가상국','quote':'없는 원문'}]}, 'test'
        with patch('kodame_intake.foundation_facts._request_json',side_effect=response):
            result=extract_plan_facts(text)
        self.assertEqual(len(result['facts']),1)
        self.assertEqual(result['facts'][0]['source_location']['page'],2)
        self.assertGreater(result['rejected_quotes'],0)
        self.assertEqual(result['coverage'][-1]['end'],len(text))

    def test_source_table_and_unicode(self):
        text='[PDF 페이지 7]\n[표 2 행 3] 농업 수확량 54% 🌾'
        loc=locate(text,'농업 수확량 54% 🌾')
        self.assertEqual((loc['page'],loc['table'],loc['table_row']),(7,2,3))
        self.assertEqual(text[loc['start']:loc['end']],'농업 수확량 54% 🌾')
        self.assertIsNone(locate(text,'없는 인용'))

    def test_suspicious_negatives_multisector(self):
        for topic in ('보건 강사','농업 수확량','교육 수료생','도로 포장'):
            item={'id':'outcome-1','indicator':topic+' 실적'}
            with self.subTest(topic=topic):
                self.assertEqual(suspicious_negatives([item],topic+' 2026년 54명',{'observations':[]}),[item])
                self.assertEqual(suspicious_negatives([item],'자료가 없음',{'observations':[]}),[])
                self.assertEqual(suspicious_negatives([item],topic+' 54',{'observations':[{'indicator_id':item['id']}]}),[])

    def test_scope_union_and_conflict(self):
        self.assertEqual(missing_ranges(100,[[30,60],[0,40],[80,90]]),[[60,80],[90,100]])
        docs=[{'fulltext_review':{'chunks':[{'evidence':[{'question_id':'a','kind':'positive'}, {'question_id':'a','kind':'limitation'}]}]}}]
        self.assertEqual(set(escalation_questions(docs,['a','b'])),{'b'})

    def test_zero_missing_and_invalid_score_distinct(self):
        self.assertEqual(score_or_none(0),0)
        for value in (None,True,'NaN',float('inf'),101,'no score'):
            self.assertIsNone(score_or_none(value))
        self.assertIn('claim_checks',review_schema()['required'])
        self.assertTrue(claim_audit({'claim_checks':[{'claim':'성공','verdict':'supported','evidence_ids':[]}]},[])['issues'])

    def test_sparse_targets_and_immutable_comparison(self):
        self.assertEqual(evidence_targets('conclusion',[]),(400,2200,'limited'))
        self.assertNotEqual(digest({'mapping':['a']}),digest({'mapping':['b']}))
        self.assertEqual(compare({'a':1},{'a':2}),[{'path':'/a','before':1,'after':2}])

    def test_identity_survives_renumbering_but_not_changed_measure(self):
        old={'tiers':[{'id':'outputs','indicators':[{'id':'outputs-1','text':'교육 수료생 30명','stable_id':'fixed'}]}]}
        new={'tiers':[{'id':'outputs','indicators':[{'id':'outputs-2','text':'교육 수료생 30명'}]}]}
        assign_identities(new,old,'p','newdoc')
        self.assertEqual(new['tiers'][0]['indicators'][0]['stable_id'],'fixed')
        new['tiers'][0]['indicators'][0]['text']='교육 수료생 60명'
        assign_identities(new,old,'p','newdoc')
        self.assertNotEqual(new['tiers'][0]['indicators'][0]['stable_id'],'fixed')

    def test_navigation_multisector_no_keyword_seed(self):
        for requirement,name in [('농업 수확량 조사','농업 수확량 조사.pdf'),('도로 포장 검수','도로 포장 검수.txt'),('교육 수료 명단','교육 수료 명단.xlsx')]:
            self.assertTrue(candidate_match(requirement,name)[0])
        self.assertFalse(candidate_match('농업 수확량','CPCR 강사 수료명단')[0])
