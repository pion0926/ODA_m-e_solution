import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from kodame_intake.dac_review import validate_selection, apply_plan, digest
from kodame_intake.dac_evidence import analyze_document


class DacReviewTests(unittest.TestCase):
    def test_scope_is_server_owned_and_rejects_foreign_or_stale_selection(self):
        plan={'ready':True,'revision':'v','input_snapshot':{},'documents':[{'id':'a','status':'completed'}],
              'indicators':[{'id':'effectiveness-q1','scopes':{'a':{'ranges':[[0,10]]}}}]}
        result=validate_selection(plan,'v',{'effectiveness-q1':['a']},[])
        self.assertEqual(result['scopes']['effectiveness-q1']['a']['ranges'],[[0,10]])
        for revision,ids in [('old',['a']),('v',['foreign']),('v',['a','a'])]:
            with self.assertRaises(HTTPException):
                validate_selection(plan,revision,{'effectiveness-q1':ids},[])

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json',return_value=({'evidence':[]},'test'))
    def test_only_reviewed_windows_and_questions_are_sent(self,call,conn):
        text='목표 10명 실적 8명\n'+'X'*40000+'보내면 안 되는 본문'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.txt';path.write_text(text,encoding='utf-8')
            doc={'id':'a','name':'data.txt','extracted_path':str(path),'assigned_criteria':['effectiveness'],
                 'question_scopes':{'effectiveness-q1':{'mode':'focused','ranges':[[0,20]]}},'scope_text':text}
            analyze_document(doc)
        self.assertEqual(call.call_count,1)
        prompt=json.loads(call.call_args.args[1])
        self.assertEqual([q['id'] for q in prompt['criteria']['effectiveness']['questions']],['effectiveness-q1'])
        self.assertNotIn('보내면 안 되는 본문',str(prompt))

    def test_unselected_document_is_excluded_and_changed_text_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.txt';path.write_text('original',encoding='utf-8')
            plan={'documents':[{'id':'a','text_digest':digest('original'),'artifact':False}],
                  'scopes':{'effectiveness-q1':{'a':{'mode':'focused','ranges':[[0,8]]}}}}
            docs=[{'id':'a','extracted_path':str(path)},{'id':'b'}]
            self.assertEqual([d['id'] for d in apply_plan(docs,plan)],['a'])
            path.write_text('changed',encoding='utf-8')
            with self.assertRaises(RuntimeError):apply_plan(docs,plan)

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json',return_value=({'evidence':[]},'test'))
    def test_full_scope_reads_beyond_intake_text_without_expanding_other_question(self,call,conn):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.txt';path.write_text('도입\n'+'X'*30000+'마지막 원문',encoding='utf-8')
            doc={'id':'a','name':'data.txt','extracted_path':str(path),'stored_path':str(path),'extension':'.txt',
                 'assigned_criteria':['effectiveness'],'scope_text':'도입',
                 'question_scopes':{'effectiveness-q1':{'mode':'focused','ranges':[[0,2]]},
                                    'effectiveness-q2':{'mode':'full','ranges':[[0,2]]}}}
            analyze_document(doc)
        prompts=[json.loads(c.args[1]) for c in call.call_args_list]
        tail=next(p for p in prompts if '마지막 원문' in str(p))
        self.assertEqual([q['id'] for q in tail['criteria']['effectiveness']['questions']],['effectiveness-q2'])
