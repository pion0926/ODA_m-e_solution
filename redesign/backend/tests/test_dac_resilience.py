import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from psycopg import OperationalError
from kodame_intake import dac_evidence as de, openrouter as provider
from kodame_intake.structured_output import parse_object, validate_schema
from kodame_intake.evaluation_storage import retry_storage


class ResilienceTests(unittest.TestCase):
    @patch('kodame_intake.dac_assessor.set_current_question')
    @patch('kodame_intake.dac_assessor.save_question')
    @patch('kodame_intake.dac_assessor._request_json')
    def test_failed_question_does_not_cancel_other_questions_and_retry_reuses_checkpoint(self,call,save,current):
        from kodame_intake.dac_assessor import assess_criterion,template
        from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
        criterion=EVALUATION_CRITERIA['relevance'];pdm={'status':'unavailable','model':{}}
        seen=[];checkpoints={}
        def checkpoint(run,qid,digest,raw):checkpoints[qid]={'digest':digest,'raw':raw}
        save.side_effect=checkpoint
        fail_first=True
        def answer(system,prompt,*args,**kwargs):
            data=json.JSONDecoder().raw_decode(prompt)[0];qid=data['questions'][0]['question_id'];seen.append(qid)
            if fail_first and qid=='relevance-q1':raise provider.AnalysisError('invalid output')
            raw=template({**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]})
            raw['question_assessments'][0]['finding']='원문 근거가 충분하지 않아 현재 질문의 성과 판단을 보류합니다.'
            return raw,'test'
        call.side_effect=answer
        with self.assertRaises(provider.AnalysisError):assess_criterion('relevance',criterion,[],{},pdm,run_id='run')
        self.assertEqual(seen,['relevance-q1']*3+['relevance-q2'])
        self.assertIn('relevance-q2',checkpoints)
        fail_first=False;seen.clear()
        result=assess_criterion('relevance',criterion,[],{},pdm,run_id='retry',checkpoints=checkpoints)
        self.assertEqual(seen,['relevance-q1'])
        self.assertEqual(len(result['question_assessments']),2)

    @patch('kodame_intake.dac_evidence.analyze_document')
    def test_failed_document_preserves_other_document_completion(self,analyze):
        partial={'status':'partial','chunks':[],'reviewed_criteria':['effectiveness']}
        def process(doc):
            if doc['id']=='bad':raise de.DocumentReviewIncomplete('retry',partial)
            return {'status':'completed','chunks':[]}
        analyze.side_effect=process
        docs=[{'id':i,'ref':i,'name':i,'assigned_criteria':['effectiveness']} for i in ('bad','good')]
        de.prepare_documents(docs,allow_partial=True)
        self.assertEqual(docs[0]['fulltext_review']['status'],'partial')
        self.assertEqual(docs[1]['fulltext_review']['status'],'completed')

    def test_server_sources_require_known_ids_and_exact_original(self):
        text='사업 실적 70명\n'+ '한글 Uzbek oʻzbek 😀 '*100
        sources=de.source_blocks(text)
        item={'question_id':'q','kind':'positive','source_ids':list(sources),'finding':'성과 원문 대조'}
        schema=de.extraction_schema({'q'},sources)
        validate_schema({'evidence':[item]},schema)
        result=de._validate_chunk({'evidence':[item]},text,{'q'},sources)
        self.assertTrue(all(r['quote'] in text and len(r['quote'])<=800 for r in result))
        self.assertEqual(len({r['quote_group'] for r in result}),1)
        for invalid in (['S9999'],[None],[],['S0001',{}]):
            with self.subTest(invalid=invalid),self.assertRaises(provider.AnalysisError):
                de._validate_chunk({'evidence':[{**item,'source_ids':invalid}]},text,{'q'},sources)

    def test_unicode_and_malformed_json_are_rejected_before_storage(self):
        self.assertEqual(parse_object('\ufeff{"text":"한글 😀 oʻzbek"}')['text'],'한글 😀 oʻzbek')
        for content in ('{"x":"\\u0000"}','{"x":"\\ud800"}','{"x":NaN}','{"x":1e999}',
                        '{"x":1,"x":2}','{"x":',None,'[]'):
            with self.subTest(content=content),self.assertRaises((ValueError,TypeError)):
                parse_object(content)

    def test_no_line_clamping_and_no_unverified_quote_fallback(self):
        for start,end in ((0,1),(1,900),(True,1),(2,1),({},1)):
            with self.subTest(start=start),self.assertRaises(provider.AnalysisError):
                de._validate_chunk({'evidence':[{'question_id':'q','kind':'context','start_line':start,'end_line':end,'finding':'test'}]},'원문',{'q'})
        r=de._validate_chunk({'evidence':[{'question_id':'q','kind':'context','start_line':'1','end_line':'1','finding':'test'}]},'원문',{'q'})
        self.assertEqual(r[0]['quote'],'원문')

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json')
    def test_partial_retry_only_requests_missing_range(self,call,conn):
        def response(system,prompt,*args,**kwargs):
            data=json.JSONDecoder().raw_decode(prompt)[0]
            if data['chunk_end']<=1200:
                raise provider.AnalysisError('invalid source id')
            return {'evidence':[]},'test'
        call.side_effect=response
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'text.txt';path.write_text('a'*2400,encoding='utf-8')
            doc={'id':'d','name':'text.txt','extracted_path':str(path),'assigned_criteria':['effectiveness'],
                 'scope_text':'a'*2400,'question_scopes':{'effectiveness-q1':{'mode':'focused','ranges':[[0,1200],[1200,2400]]}}}
            with self.assertRaises(provider.AnalysisError):de.analyze_document(doc)
            cached=conn.return_value.__enter__.return_value.execute.call_args.args[1][0].obj
            self.assertEqual(cached['status'],'partial')
            self.assertEqual([(c['start'],c['end']) for c in cached['chunks']],[(1200,2400)])
            doc['dac_fulltext_cache']=cached
            call.reset_mock();call.side_effect=None;call.return_value=({'evidence':[]},'test')
            result=de.analyze_document(doc)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(call.call_count,1)
            sent=json.loads(call.call_args.args[1])
            self.assertEqual((sent['chunk_start'],sent['chunk_end']),(0,1200))

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json')
    def test_output_limit_splits_immediately(self,call,conn):
        seen=[]
        def response(system,prompt,*args,**kwargs):
            p=json.loads(prompt);seen.append((p['chunk_start'],p['chunk_end']))
            if p['chunk_end']-p['chunk_start']>3000:raise provider.OutputLimitError('length')
            return {'evidence':[]},'test'
        call.side_effect=response
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'text.txt';path.write_text('a'*5000,encoding='utf-8')
            result=de.analyze_document({'id':'d','name':'text.txt','extracted_path':str(path),'assigned_criteria':['effectiveness']})
        self.assertEqual(seen.count((0,5000)),1)
        self.assertEqual(result['status'],'completed')

    @patch('kodame_intake.evaluation_storage.time.sleep')
    def test_storage_retries_same_result_without_ai(self,sleep):
        calls=[]
        @retry_storage
        def store():
            calls.append(1)
            if len(calls)<3:raise OperationalError('temporary db failure')
            return 'saved'
        self.assertEqual(store(),'saved');self.assertEqual(len(calls),3)

    @patch('kodame_intake.openrouter.time.sleep')
    @patch('kodame_intake.openrouter.record_token_usage')
    @patch('kodame_intake.openrouter.OPENROUTER_API_KEY','test')
    @patch('kodame_intake.openrouter.httpx.Client')
    def test_provider_fault_classification(self,factory,usage,sleep):
        client=factory.return_value.__enter__.return_value
        def response(code,body,headers=None):
            return httpx.Response(code,json=body,headers=headers,request=httpx.Request('POST','https://example.invalid'))
        success=response(200,{'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]})
        for code in (408,429,500,502,503,504):
            client.reset_mock();client.post.side_effect=[response(code,{}),success]
            self.assertTrue(provider._request_json('s','u','KODAME DAC Full Document Review')[0]['ok'])
            self.assertEqual(client.post.call_count,2)
        for transient in ({'error':{'code':503}}, {'choices':[{'finish_reason':'error','message':{}}]}):
            client.reset_mock();client.post.side_effect=[response(200,transient),success]
            self.assertTrue(provider._request_json('s','u','KODAME DAC Full Document Review')[0]['ok'])
            self.assertEqual(client.post.call_count,2)
        client.reset_mock();client.post.side_effect=None;client.post.return_value=response(503,{})
        with self.assertRaises(provider.ProviderTransientError):provider._request_json('s','u','KODAME DAC Full Document Review')
        self.assertEqual(client.post.call_count,3)
        cases=[(response(401,{'error':{'message':'invalid key'}}),provider.ConfigurationError),
               (response(402,{'error':{}}),provider.BillingError),
               (response(400,{'error':{'message':'maximum context length exceeded'}}),provider.ContextLimitError),
               (response(200,[]),provider.AnalysisError),
               (response(200,{'choices':[{'message':None}]}),provider.AnalysisError),
               (response(200,{'choices':[{'message':{'content':'{}'},'finish_reason':'length'}]}),provider.OutputLimitError),
               (response(200,{'choices':[{'message':{'refusal':'no'},'finish_reason':'content_filter'}]}),provider.RefusalError)]
        for result,error in cases:
            client.post.side_effect=None;client.post.return_value=result
            with self.subTest(error=error),self.assertRaises(error):provider._request_json('s','u','KODAME DAC Full Document Review')
        client.reset_mock();client.post.side_effect=httpx.ReadTimeout('timeout')
        with self.assertRaises(provider.ProviderTransientError):provider._request_json('s','u','KODAME DAC Full Document Review')
        self.assertEqual(client.post.call_count,3)
