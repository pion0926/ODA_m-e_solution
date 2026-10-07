import copy
import json
from unittest.mock import patch
import pytest
from kodame_intake import dac_evidence_selection as selection
from kodame_intake.openrouter import AnalysisError


def fact(ident, **extra):
    return {'evidence_id':ident,'quote':'실적 6명 / 목표 10명, 진행 중. 한글 oʻzbek 😀',
            'file_name':'실적.pdf','question_id':'effectiveness-q1','finding':'원문 사실',
            'kind':'positive', **extra}


def test_compaction_is_lossless_for_quotes_and_does_not_mutate_source():
    prompt={'evidence':[fact('E1'),fact('E2',kind='limitation')]}
    before=copy.deepcopy(prompt)
    result=selection.compact(prompt)
    quotes={q['id']:q['text'] for q in result['source_quotes']}
    assert [quotes[f['quote_ref']] for f in result['evidence']]==[f['quote'] for f in before['evidence']]
    assert len(quotes)==1 and prompt==before


def test_selection_reviews_every_group_and_keeps_table_rows_and_counterevidence():
    facts=[fact('E1',quote_group='shared'),fact('E2',quote_group='shared'),
           fact('E3',kind='limitation'),fact('T1',table_row_candidate=True)]
    prompt={'questions':[{'id':'q'}], 'evidence':facts,'allowed_evidence_ids':[f['evidence_id'] for f in facts]}
    seen=[]
    def answer(system,user,*args,**kwargs):
        data=json.JSONDecoder().raw_decode(user)[0]
        seen.extend(f['evidence_id'] for f in data['evidence'])
        return {'evidence_ids':['E1','E3']},'test'
    with patch.object(selection,'_request_json',side_effect=answer):
        result=selection.prepare_prompt(prompt,force=True)
    assert set(seen)=={'E1','E2','E3'}
    assert set(result['allowed_evidence_ids'])=={'E1','E2','E3','T1'}
    assert result['evidence_selection']['reviewed_count']==4
    assert result['evidence_selection']['mandatory_table_rows']==1


@pytest.mark.parametrize('ids',[['invented'],[],['E1']])
def test_invalid_or_counterevidence_erasing_selection_fails_closed(ids):
    with patch.object(selection,'_request_json',return_value=({'evidence_ids':ids},'test')) as request:
        with pytest.raises(AnalysisError):
            selection.select_batch({},[fact('E1'),fact('E2',kind='limitation')],run_id=None,saved={})
        assert request.call_count==3


def test_durable_selection_reuses_identical_model_question_and_sources():
    saved={}
    with patch.object(selection,'_request_json',return_value=({'evidence_ids':['E1']},'test')) as request, \
         patch.object(selection,'save_selection',side_effect=lambda run,digest,raw:saved.update({digest:raw})):
        assert selection.select_batch({},[fact('E1')],run_id='run',saved={})=={'E1'}
        assert selection.select_batch({},[fact('E1')],run_id='retry',saved=saved)=={'E1'}
        assert request.call_count==1


def test_assessor_prompt_upgrade_reuses_source_selection_without_reselecting():
    saved = {}
    prompt = {'prompt_version': 'dac-fact-judgement-v14-contextual',
              'questions': [{'id': 'effectiveness-q1'}],
              'evidence': [fact('E1')], 'allowed_evidence_ids': ['E1']}
    with patch.object(selection, '_request_json', return_value=({'evidence_ids': ['E1']}, 'test')) as request, \
         patch.object(selection, 'save_selection', side_effect=lambda run, digest, raw: saved.update({digest: raw})):
        first = selection.prepare_prompt(prompt, run_id='old-run', force=True)
        prompt['prompt_version'] = 'dac-fact-judgement-v15-scope-conflict'
        second = selection.prepare_prompt(prompt, run_id='new-run', saved=saved, force=True)
    assert first['allowed_evidence_ids'] == second['allowed_evidence_ids'] == ['E1']
    assert request.call_count == 1
