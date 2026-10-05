import unittest
from unittest.mock import patch
from kodame_intake.intake_facts import ground_facts
from kodame_intake.evidence_matching import match_foundations


class FactTests(unittest.TestCase):
    def fact(self, **changes):
        return dict(statement='강사 6명 양성 보고',kind='reported_actual',value='6명',unit='명',period='',population='',
                    evidence_quote='강사 6명 양성',pdm_indicator_ids=['outputs-1'],dac_question_ids=['effectiveness-q1'],**changes)

    def ground(self, items, text='강사 6명 양성', artifact=False):
        return ground_facts(items,text,start=100,indicators=['outputs-1'],questions=['effectiveness-q1'],artifact=artifact)

    def test_grounding_and_whitespace_offsets(self):
        result = self.ground([self.fact()], '앞\n강사 6명\n양성 뒤')[0]
        self.assertEqual(result['evidence_quote'], '강사 6명\n양성')
        self.assertEqual(result['source_start'], 102)
        self.assertEqual(result['verification'], 'source_quote_verified')

    def test_unverified_facts_do_not_fail_registration(self):
        for changes in ({'evidence_quote':'없는 문장'}, {'value':'60명'},
                        {'pdm_indicator_ids':['unknown'],'dac_question_ids':[]}):
            item={**self.fact(),**changes}
            self.assertEqual(self.ground([item]), [])
        self.assertEqual(self.ground([self.fact()], artifact=True), [])

    def test_facts_create_mapping_and_contextual_summary(self):
        context={'sources':{'pdm':{'id':'p'},'project_plan':{'id':'plan'}},'plan_text':'강사 양성 사업',
                 'indicators':[{'id':'outputs-1','text':'강사 수','mov':'명단','tier':'outputs'}]}
        payload={'project_plan':[],'pdm':[],'facts':[self.fact()], 'document_role':'강사 양성 활동의 보고 실적을 제시하는 자료다. 명단 대조가 필요하다.'}
        with patch('kodame_intake.evidence_matching._request_json', return_value=(payload,'test')):
            result=match_foundations('강사 6명 양성',context=context)
        self.assertEqual(result['pdm'][0]['indicator_id'],'outputs-1')
        self.assertEqual(result['registration_facts']['summary'],payload['document_role'])
        self.assertEqual(len(result['registration_facts']['facts']),1)
        self.assertNotIn('achievement_rate', result)

    def test_dac_review_uses_late_registered_fact(self):
        from kodame_intake.dac_review import select_ranges
        text='가'*20000+'강사 6명 양성'+'나'*4000
        ranges=select_ranges(text,{'id':'effectiveness-q1','question':'성과'},
            {'registration_facts':{'facts':[self.fact()]}})
        self.assertTrue(any(start <= 20000 < end for start,end in ranges))

    def test_spreadsheet_source_ids_preserve_cells_and_generate_mapping(self):
        import json
        text='[시트: Sheet1]\nA1=프로그램 | B1=목표 | C1=실적\nA2=CPCR 강사 양성 | B2=10명 | C2=6명\n'
        context={'sources':{'pdm':{'id':'p'},'project_plan':{'id':'plan'}},'plan_text':'강사 양성 사업',
                 'indicators':[{'id':'outputs-1','text':'강사 수','mov':'명단','tier':'outputs'}]}
        def reply(system, prompt, title, **kwargs):
            sources=json.loads(prompt)['evidence_sources']
            selected=next(source for source in sources if 'C2=6명' in source['text'])
            fact={**self.fact(),'source_id':selected['source_id']}
            fact.pop('evidence_quote')
            invalid={**fact,'value':'60명'}
            unknown={**fact,'source_id':'S9999','evidence_quote':'강사 6명 양성'}
            return {'document_role':'실적 현황', 'facts':[fact,invalid,unknown],'project_plan':[],'pdm':[]},'test'
        with patch('kodame_intake.evidence_matching._request_json', side_effect=reply):
            result=match_foundations(text,context=context)
        self.assertEqual(len(result['registration_facts']['facts']),1)
        self.assertEqual(result['registration_facts']['discarded_fact_count'],2)
        self.assertIn('C2=6명',result['pdm'][0]['evidence_quote'])
        self.assertIn(result['pdm'][0]['evidence_quote'],text)
