import copy
import unittest
from unittest.mock import patch

from kodame_intake.dac_rules import score_question
from kodame_intake.dac_assessor import assess_criterion, template
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from tests import test_dac_rules as fixtures


class CorroborationRecoveryTests(unittest.TestCase):
    def test_optional_bad_groups_do_not_abort_or_inflate_score(self):
        bad_values = [None, '기관', {}, ['기관'], [None], [{}]]
        for ids in ([], None, 'E1', ['missing'], ['E2'], [['E1']], ['E1', 'missing']):
            bad_values.append([{'name':'A','provenance':'독립적으로 수집된 조사 결과입니다.','evidence_ids':ids}])
        for name, provenance in (('', '독립적으로 수집된 조사 결과입니다.'), (None, '독립적으로 수집된 조사 결과입니다.'), ('A', None), ('A','짧음')):
            bad_values.append([{'name':name,'provenance':provenance,'evidence_ids':['E1']}])
        for value in bad_values:
            with self.subTest(value=value):
                item,evidence=fixtures.DacRuleEngineTests().fixture()
                baseline=score_question('relevance-q1',item,evidence)
                item['indicators'][0]['source_families']=value
                before=copy.deepcopy(item)
                result=score_question('relevance-q1',item,evidence)
                check=result['checks'][0]
                self.assertFalse(check['quality']['independent_corroboration'])
                self.assertEqual(check['source_families'],[])
                self.assertEqual(result['selected_score'],baseline['selected_score'])
                self.assertEqual(item,before)
                if value is not None:self.assertTrue(check['applied_rules'])

    def test_valid_but_unselected_evidence_is_not_promoted(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture()
        evidence['EX']={**evidence['E1'],'source_sha256':'shaX','document_id':'dx'}
        item['indicators'][0]['source_families']=[{'name':'A','provenance':'독립적으로 수집된 조사 결과입니다.','evidence_ids':['E1','EX']}]
        check=score_question('relevance-q1',item,evidence)['checks'][0]
        self.assertEqual(check['evidence_ids'],['E1'])
        self.assertEqual(check['source_families'],[])

    def test_valid_independent_groups_still_receive_credit(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture()
        evidence['EX']={**evidence['E1'],'source_sha256':'shaX','document_id':'dx'}
        fact=item['indicators'][0];fact['evidence_ids']=['E1','EX']
        fact['source_families']=[{'name':name,'provenance':'독립적으로 수집된 조사 결과입니다.','evidence_ids':[eid]} for name,eid in [('A','E1'),('B','EX')]]
        check=score_question('relevance-q1',item,evidence)['checks'][0]
        self.assertTrue(check['quality']['independent_corroboration'])
        self.assertEqual(len(check['source_families']),2)

    def test_bad_primary_evidence_remains_a_validation_failure(self):
        item,evidence=fixtures.DacRuleEngineTests().fixture()
        item['indicators'][0]['evidence_ids']=['missing']
        with self.assertRaises(ValueError):score_question('relevance-q1',item,evidence)

    def test_assessment_continues_without_retry_for_optional_group_error(self):
        criterion=EVALUATION_CRITERIA['relevance']
        def answer(system,prompt,title,**kwargs):
            import json
            qid=json.loads(prompt.strip())['questions'][0]['question_id']
            raw=template({**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]})
            q=raw['question_assessments'][0]
            q['finding']='제공된 근거가 부족하여 실행 성과를 판단할 수 없습니다.'
            q['indicators'][0]['source_families']=[{'name':'A','provenance':'독립적으로 수집된 조사 결과입니다.','evidence_ids':['missing']}]
            return raw,'test'
        with patch('kodame_intake.dac_assessor._request_json',side_effect=answer) as request:
            result=assess_criterion('relevance',criterion,[],{}, {'status':'unavailable','model':{}})
        self.assertEqual(request.call_count,len(criterion['questions']))
        self.assertIsNone(result['score'])


if __name__=='__main__':unittest.main()
