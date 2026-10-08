import copy
import hashlib
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


def reordered(value):
    if isinstance(value, dict):
        return {key: reordered(value[key]) for key in sorted(value, key=lambda key: (len(key.encode()), key))}
    if isinstance(value, list):
        return [reordered(item) for item in value]
    return value


def legacy_key(question, facts):
    return hashlib.sha256(selection.encoded([selection.VERSION, selection.current_llm_model(),
        {'question': question, 'evidence': facts}]).encode()).hexdigest()


def test_fresh_to_jsonb_key_order_roundtrip_reuses_exact_facts():
    question = {'question_id': 'effectiveness-q1', 'definition': {'name': '성과', 'checks': ['a', 'b']}}
    facts = [fact('E1', locator={'section': '본문', 'chunk_start': 0, 'chunk_end': 12}), fact('E2', kind='limitation')]
    loaded_question, loaded_facts = reordered(question), reordered(facts)
    assert facts == loaded_facts and question == loaded_question
    assert legacy_key(question, facts) != legacy_key(loaded_question, loaded_facts)
    saved = {}
    with patch.object(selection, '_request_json', return_value=({'evidence_ids': ['E1', 'E2']}, 'test')) as request, \
         patch.object(selection, 'save_selection', side_effect=lambda run, digest, raw: saved.update({digest: raw})):
        assert selection.select_batch(question, facts, run_id='fresh', saved={}) == {'E1', 'E2'}
        assert selection.select_batch(loaded_question, loaded_facts, run_id='jsonb', saved=saved) == {'E1', 'E2'}
    assert request.call_count == 1
    assert len(saved) == 1


def test_exact_legacy_hit_is_validated_and_promoted_then_survives_key_reordering():
    question, facts = {'id': 'q', 'question': '검토'}, [fact('E1')]
    old_key = legacy_key(question, facts)
    saved = {old_key: {'evidence_ids': ['E1']}}
    with patch.object(selection, '_request_json') as request, \
         patch.object(selection, 'save_selection', side_effect=lambda run, digest, raw: saved.update({digest: raw})) as save:
        assert selection.select_batch(question, facts, run_id='migration', saved=saved) == {'E1'}
        canonical_key = save.call_args.args[1]
        assert canonical_key != old_key
        assert selection.select_batch(reordered(question), reordered(facts), run_id='next', saved=saved) == {'E1'}
    request.assert_not_called()
    assert save.call_count == 2


@pytest.mark.parametrize('ids', [['invented'], []])
def test_legacy_selection_must_still_preserve_allowed_ids_and_counterevidence(ids):
    facts = [fact('E1', kind='limitation')]
    saved = {legacy_key({}, facts): {'evidence_ids': ids}}
    with patch.object(selection, '_request_json', return_value=({'evidence_ids': ['E1']}, 'test')) as request:
        assert selection.select_batch({}, facts, run_id=None, saved=saved) == {'E1'}
    assert request.call_count == 1


def test_different_legacy_key_order_is_not_guessed_or_promoted():
    facts = [fact('E1')]
    saved = {legacy_key({}, facts): {'evidence_ids': ['E1']}}
    loaded = reordered(facts)
    assert legacy_key({}, facts) != legacy_key({}, loaded)
    with patch.object(selection, '_request_json', return_value=({'evidence_ids': ['E1']}, 'test')) as request:
        assert selection.select_batch({}, loaded, run_id=None, saved=saved) == {'E1'}
    assert request.call_count == 1


@pytest.mark.parametrize('change', ['quote', 'question', 'model'])
def test_canonical_cache_still_invalidates_changed_evaluation_inputs(change):
    facts, question, saved = [fact('E1')], {'id': 'q'}, {}
    with patch.object(selection, '_request_json', return_value=({'evidence_ids': ['E1']}, 'test')) as request, \
         patch.object(selection, 'save_selection', side_effect=lambda run, digest, raw: saved.update({digest: raw})), \
         patch.object(selection, 'current_llm_model', return_value='model-one') as model:
        selection.select_batch(question, facts, run_id='first', saved={})
        if change == 'quote': facts[0]['quote'] += ' 추가 원문'
        elif change == 'question': question['id'] = 'different-question'
        else: model.return_value = 'model-two'
        selection.select_batch(question, facts, run_id='second', saved=saved)
    assert request.call_count == 2
