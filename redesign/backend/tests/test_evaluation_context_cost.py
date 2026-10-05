import copy
import json
from unittest.mock import patch

from kodame_intake.dac_scope_policy import escalation_questions, expand_documents
from kodame_intake.report_evaluation_context import for_report


def test_limitation_is_evidence_not_a_conflict_trigger():
    docs = [{'fulltext_review': {'chunks': [{'evidence': [
        {'question_id': 'a', 'kind': 'positive'}, {'question_id': 'a', 'kind': 'limitation'},
        {'question_id': 'b', 'kind': 'limitation'}, {'question_id': 'c', 'kind': 'context'},
    ]}]}}]
    assert set(escalation_questions(docs, ['a', 'b', 'c', 'd'])) == {'c', 'd'}


def test_expansion_keeps_existing_scope_and_does_not_read_unrelated_books(tmp_path):
    path = tmp_path / 'text.txt'
    path.write_text(('정책 정합성과 수요 조사 내용. ' * 10000), encoding='utf-8')
    docs = [{'id': 'plan', 'extracted_path': str(path), 'assigned_criteria': ['relevance']},
            {'id': 'textbook', 'extracted_path': str(path), 'assigned_criteria': ['effectiveness']}]
    scopes = {'relevance-q1': {'mode': 'focused', 'ranges': [[0, 5000]]}}
    review = {'status': 'completed', 'chunks': [{'start': 0, 'end': 5000}]}
    reviewed = [{**docs[0], 'question_scopes': scopes, 'fulltext_review': review}]
    with patch('kodame_intake.dac_review.select_ranges', return_value=[[8000, 13000]]) as select:
        expanded = expand_documents(docs, reviewed, {'relevance-q1': '근거 부족'})
    assert [d['id'] for d in expanded] == ['plan']
    assert expanded[0]['question_scopes']['relevance-q1']['ranges'] == [[0, 5000], [8000, 13000]]
    assert expanded[0]['dac_fulltext_cache'] == review
    assert select.call_args.kwargs['excluded_ranges'] == [[0, 5000]]


def test_report_preserves_all_decisions_numbers_and_adverse_sources_without_mutating_storage():
    checks = [{'state': 'conflicted', 'finding': '같은 기간 실적 6명과 8명이 충돌',
               'measurements': [{'target': 10, 'actual': 6, 'due': False}],
               'negative_fact_quote': '목표를 충족하지 못했다', 'evidence_ids': ['E1', 'E2']}]
    source = [{'criterion_id': 'effectiveness', 'score': None, 'question_assessments': [{
        'score': None, 'finding': '자료 충돌로 보류', 'scoring_trace': {'checks': checks, 'selected_score': None},
        'limitations': ['독립 검증 없음'], 'table_row_reviews': [{'evidence_id': 'E2', 'decision': 'excluded'}],
        'evidence_quotes': [{'evidence_id': 'E1', 'document_id': 'd1', 'quote': '원문' * 10000, 'kind': 'limitation'}],
    }]}]
    original = copy.deepcopy(source)
    compact = for_report(source)
    q = compact[0]['question_assessments'][0]
    assert compact[0]['score'] is None and q['score'] is None
    assert q['scoring_trace']['checks'] == checks
    assert q['limitations'] == ['독립 검증 없음']
    assert q['table_row_reviews'] == source[0]['question_assessments'][0]['table_row_reviews']
    assert q['validated_source_references'][0]['kind'] == 'limitation'
    assert source == original
    assert len(json.dumps(compact)) < len(json.dumps(source)) / 10


def test_dac_scope_change_reuses_only_identical_source_and_model(tmp_path):
    from kodame_intake.dac_evidence import analyze_document
    path = tmp_path / 'source.txt'
    text = '정책 정합성과 수요 분석. ' * 1000
    path.write_text(text, encoding='utf-8')
    doc = {'id': 'doc', 'name': '사업계획서', 'sha256': 'same-source', 'extracted_path': str(path),
           'assigned_criteria': ['relevance'], 'scope_text': text,
           'question_scopes': {'relevance-q1': {'mode': 'focused', 'ranges': [[0, 4000]]}}}
    with patch('kodame_intake.dac_evidence.connection'), patch('kodame_intake.intake_control.check'), \
         patch('kodame_intake.dac_evidence.current_llm_model', return_value='model-a'), \
         patch('kodame_intake.dac_evidence._request_json', return_value=({'evidence': []}, 'model-a')) as request:
        first = analyze_document(doc)
        assert request.call_count == 1
        doc['dac_fulltext_cache'] = first
        doc['question_scopes']['relevance-q1']['ranges'].append([8000, 12000])
        request.reset_mock()
        second = analyze_document(doc)
        assert request.call_count == 1
        prompt = json.loads(request.call_args.args[1])
        assert (prompt['chunk_start'], prompt['chunk_end']) == (8000, 12000)
        assert len(second['chunks']) == 2
        doc['dac_fulltext_cache'] = second
        doc['question_scopes']['relevance-q1']['ranges'] = [[0, 4000]]
        request.reset_mock()
        narrower = analyze_document(doc)
        assert request.call_count == 0
        assert [(c['start'], c['end']) for c in narrower['chunks']] == [(0, 4000)]
        doc['question_scopes']['relevance-q1']['ranges'].append([8000, 12000])
        request.reset_mock()
        with patch('kodame_intake.dac_evidence.current_llm_model', return_value='model-b'):
            analyze_document(doc)
        assert request.call_count == 2
        request.reset_mock()
        doc['scope_text'] = text.replace('정책', '전략')
        analyze_document(doc)
        assert request.call_count == 2
