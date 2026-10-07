"""Semantic cache boundaries for repeated DAC evaluations (no external AI)."""
import copy
import json
from unittest.mock import patch

import pytest

from kodame_intake import dac_assessor as assessor
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from kodame_intake.evaluation_recovery import load_question_candidates
from kodame_intake.evaluation_runner import _corpus
from kodame_intake.llm_models import llm_model_context


CRITERION = EVALUATION_CRITERIA['relevance']
PDM = {'status': 'completed', 'source_document_id': 'pdm-source',
       'performance_analysis_status': 'current',
       'model': {'performance_indicators': [{'id': 'p1', 'indicator': '훈련 횟수', 'actual': 1}]}}
ASSESSMENT = {'assessment_as_of': '2026-10-08', 'project_status': 'ongoing',
              'project_period': '2025.01.01 ~ 2026.12.31'}


def source(ident, qid, *, facts=True):
    return {'document_id': ident, 'sha256': 'sha-' + ident, 'ref': 'D001',
            'file_name': ident + '.pdf', 'summary': '검토한 원문 증빙',
            'fulltext_review': {'status': 'completed', 'chunk_count': 3},
            'question_reviews': {qid: {'status': 'completed', 'ranges': [[0, 500]],
                                       'source_sha256': 'sha-' + ident, 'mode': 'focused'}},
            'question_evidence': ([{'question_id': qid, 'kind': 'positive',
                                   'quote': '해당 지역의 우선 수요를 확인하고 관계 기관과 협의했다.',
                                   'finding': '관계 기관과 실제 협의한 사실이 기록에 나타납니다.'}]
                                  if facts else [])}


class Harness:
    def __init__(self):
        self.cache = {}
        self.calls = []
        self.prompts = []

    def answer(self, system, prompt, title, **kwargs):
        data = json.JSONDecoder().raw_decode(prompt)[0]
        qid = data['questions'][0]['question_id']
        self.calls.append(qid)
        self.prompts.append(data)
        raw = assessor.template({**CRITERION, 'questions': [q for q in CRITERION['questions'] if q['id'] == qid]})
        raw['question_assessments'][0]['finding'] = '원문에 해당 지표의 실행 결과가 충분하지 않아 판정을 보류합니다.'
        return raw, 'synthetic'

    def save(self, run, qid, digest, raw):
        self.cache[qid] = {'digest': digest, 'raw': copy.deepcopy(raw)}

    def run(self, corpus, *, assessment=None, pdm=None, model='openai/gpt-5.6-luna', candidates=None):
        previous = copy.deepcopy(self.cache if candidates is None else candidates)
        self.calls.clear()
        with patch.object(assessor, '_request_json', side_effect=self.answer), \
             patch.object(assessor, 'save_question', side_effect=self.save), \
             patch.object(assessor, 'record_question_reuse') as reused, \
             patch.object(assessor, 'set_current_question'), llm_model_context(model):
            result = assessor.assess_criterion('relevance', CRITERION, corpus,
                ASSESSMENT if assessment is None else assessment, PDM if pdm is None else pdm,
                run_id='new-run', checkpoints=previous)
            return result, reused.call_count


def test_new_relevant_document_only_reevaluates_affected_question():
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    before, _ = h.run(corpus)
    after, reused = h.run(corpus + [source('new-q1', 'relevance-q1')])
    assert h.calls == ['relevance-q1'] and reused == 1
    assert before['question_assessments'][1] == after['question_assessments'][1]
    # The other question never receives the irrelevant document's metadata.
    assert {d['name'] for d in h.prompts[1]['document_review']} == {'q2.pdf'}


def test_new_unrelated_document_and_upload_order_do_not_invalidate_questions():
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    h.run(corpus)
    corpus.reverse()
    for item in corpus:
        item['ref'] = 'D999'
        item['fulltext_review']['chunk_count'] = 20  # unrelated question's review
    _, reused = h.run([source('irrelevant', 'sustainability-q1')] + corpus)
    assert not h.calls and reused == 2


@pytest.mark.parametrize('change', ['new_empty_review', 'removed', 'scope', 'source', 'counterevidence'])
def test_scope_empty_reviews_and_adverse_evidence_invalidate_exact_question(change):
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    h.run(corpus)
    if change == 'new_empty_review':
        corpus.append(source('empty', 'relevance-q1', facts=False))
    elif change == 'removed':
        corpus.pop(0)
    elif change == 'scope':
        corpus[0]['question_reviews']['relevance-q1']['ranges'] = [[0, 1000]]
    elif change == 'source':
        corpus[0]['sha256'] = 'replaced-source'
    else:
        corpus[0]['question_evidence'].append({'question_id': 'relevance-q1', 'kind': 'limitation',
            'quote': '합의가 이루어지지 않아 실행을 취소했다.', 'finding': '취소된 실행 사실이 확인됩니다.'})
    h.run(corpus)
    assert h.calls == ['relevance-q1']


@pytest.mark.parametrize('change', ['date', 'phase', 'pdm_actual', 'pdm_source', 'model', 'rule', 'system'])
def test_context_changes_cannot_reuse_stale_judgments(change):
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    h.run(corpus)
    assessment, pdm, model = copy.deepcopy(ASSESSMENT), copy.deepcopy(PDM), 'openai/gpt-5.6-luna'
    if change == 'date':
        assessment['assessment_as_of'] = '2026-10-09'
    elif change == 'phase':
        assessment['project_status'] = 'ended'
    elif change == 'pdm_actual':
        pdm['model']['performance_indicators'][0]['actual'] = 2
    elif change == 'pdm_source':
        pdm['source_document_id'] = 'replacement-pdm'
    elif change == 'model':
        model = 'google/gemini-3.5-flash-lite'
    with patch.object(assessor, 'RULE_DIGEST', 'changed-rule' if change == 'rule' else assessor.RULE_DIGEST), \
         patch.object(assessor, 'SYSTEM_PROMPT', 'changed-prompt' if change == 'system' else assessor.SYSTEM_PROMPT):
        h.run(corpus, assessment=assessment, pdm=pdm, model=model)
    assert h.calls == ['relevance-q1', 'relevance-q2']


def test_changed_snapshot_id_alone_preserves_semantically_identical_pdm():
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    h.run(corpus)
    _, reused = h.run(corpus, pdm={**PDM, 'snapshot_id': 'resaved-same-model', 'created_at': 'later'})
    assert not h.calls and reused == 2


def test_invalid_cached_citations_are_rechecked_and_regenerated():
    h = Harness()
    corpus = [source('q1', 'relevance-q1'), source('q2', 'relevance-q2')]
    h.run(corpus)
    h.cache['relevance-q1']['raw']['question_assessments'][0]['indicators'][0]['evidence_ids'] = ['E-not-in-this-question']
    h.run(corpus)
    assert h.calls == ['relevance-q1']


def test_candidate_history_is_project_scoped_and_newest_digest_wins():
    rows = [{'id': 'new', 'checkpoints': {'q': {'digest': 'a', 'raw': {'version': 'new'}}}, 'selections': {'sel': {'new': True}}},
            {'id': 'old', 'checkpoints': {'q': {'digest': 'a', 'raw': {'version': 'old'}},
                                         'q2': {'digest': 'b', 'raw': {}}}, 'selections': {'sel': {'new': False}}}]
    with patch('kodame_intake.evaluation_recovery.connection') as connection:
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = rows
        checkpoints, selections = load_question_candidates('current')
        query, params = conn.execute.call_args.args
    assert 'project_id=(SELECT project_id FROM evaluation_runs WHERE id=%s)' in query
    assert params == ('current', 'current')
    assert len(checkpoints['q']) == 1 and checkpoints['q'][0]['source_run_id'] == 'new'
    assert checkpoints['q'][0]['raw']['version'] == 'new'
    assert checkpoints['q2'][0]['digest'] == 'b'
    assert selections['sel'] == {'new': True}


def test_partial_document_failure_only_blocks_question_with_missing_range():
    # One source serves two questions. q2's window was saved before q1's
    # provider failure; its completed judgment must still be checkpointed.
    doc = {'id': 'partial-doc', 'ref': 'D001', 'name': '합성 원문.txt', 'sha256': 'sha',
           'summary': '합성 자료', 'document_type': 'report', 'period': '',
           'organizations': [], 'quality_flags': [], 'assigned_criteria': ['relevance'],
           'question_scopes': {'relevance-q1': {'mode': 'focused', 'ranges': [[0, 100]]},
                               'relevance-q2': {'mode': 'focused', 'ranges': [[100, 200]]}},
           'fulltext_review': {'status': 'partial', 'character_count': 200,
               'reviewed_criteria': ['relevance'],
               'chunks': [{'start': 100, 'end': 200, 'reviewed_questions': ['relevance-q2'], 'evidence': []}]}}
    corpus, _ = _corpus('relevance', [doc])
    assert corpus[0]['question_reviews']['relevance-q1']['status'] == 'partial'
    assert corpus[0]['question_reviews']['relevance-q2']['status'] == 'completed'
    h = Harness()
    with pytest.raises(assessor.AnalysisError, match='relevance-q1.*원문 검토 미완료'):
        h.run(corpus)
    assert h.calls == ['relevance-q2']
    assert set(h.cache) == {'relevance-q2'}
