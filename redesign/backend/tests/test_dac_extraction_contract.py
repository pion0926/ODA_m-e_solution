"""Scoring-only upgrades reuse raw facts; extraction changes never do (no AI)."""
import copy
import hashlib
import json
from unittest.mock import patch

import pytest

from kodame_intake import dac_evidence as review
from kodame_intake.llm_models import llm_model_context


MODEL = 'openai/gpt-5.6-luna'
LEGACY_RULE = '562164e5bf9722da9f882a0c96cf877dbd46774684ec0a816cf0616b48daa812'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def legacy_document(tmp_path, *, scopes=None):
    text = '합성 사업에서 공동 실습을 실시하였다. 관계 기관이 참여하였다.'
    path = tmp_path / 'synthetic.txt'
    path.write_text(text, encoding='utf-8')
    criteria = {'effectiveness': review.EVALUATION_CRITERIA['effectiveness']}
    if scopes is not None:
        criteria = {k: {**v, 'questions': [q for q in v['questions'] if q['id'] in scopes]}
                    for k, v in criteria.items()}
    qids = [q['id'] for c in criteria.values() for q in c['questions']]
    end = len(text) if scopes is None else max(e for scope in scopes.values() for _, e in scope['ranges'])
    # This is the released v3 algorithm, independently reconstructed. A cache
    # minted with the new function would not prove legacy compatibility.
    cache = {'status': 'completed', 'rubric_digest': LEGACY_RULE,
        'digest': digest({'version': 'dac-fulltext-v3', 'rubric': LEGACY_RULE,
            'model': MODEL, 'criteria': criteria, 'text': text, 'scopes': scopes}),
        'reuse_identity': digest({'version': 'dac-fulltext-v3', 'rubric': LEGACY_RULE,
            'model': MODEL, 'criteria': review.EVALUATION_CRITERIA, 'text': text,
            'source_sha256': 'same-source', 'artifact': False}),
        'chunks': [{'start': 0, 'end': end, 'reviewed_questions': qids,
            'evidence': [{'question_id': qids[0], 'quote': text[:end],
                         'finding': '직접 확인한 합성 활동 사실', 'kind': 'positive'}]}]}
    doc = {'id': 'synthetic', 'name': 'synthetic.txt', 'extracted_path': str(path),
        'sha256': 'same-source', 'assigned_criteria': ['effectiveness'], 'dac_fulltext_cache': cache}
    if scopes is not None:
        doc.update(question_scopes=scopes, scope_text=text)
    return doc


@pytest.mark.parametrize('version', sorted(review.EXTRACTION_COMPATIBLE_VERSIONS))
def test_audited_scoring_versions_reuse_legacy_completed_facts(tmp_path, version):
    doc = legacy_document(tmp_path)
    rules = {**review.RULES, 'version': version, 'adaptation': 'Only scoring guidance changed'}
    with patch.object(review, 'RULES', rules), llm_model_context(MODEL), \
         patch.object(review, '_request_json') as request:
        assert review.analyze_document(doc) is doc['dac_fulltext_cache']
    request.assert_not_called()
    assert review.RULE_DIGEST != LEGACY_RULE  # Judgment still uses the new policy.


@pytest.mark.parametrize('change', ['question', 'state', 'system', 'schema',
    'implementation', 'window', 'unknown_release', 'text', 'model', 'source', 'artifact'])
def test_changed_extraction_conditions_really_call_extractor(tmp_path, change):
    doc = legacy_document(tmp_path)
    rules = copy.deepcopy(review.RULES)
    system, schema = review.EXTRACTION_SYSTEM_PROMPT, review.extraction_schema
    implementation = review._extraction_implementation_digest()
    window, model = review.CHUNK_SIZE, MODEL
    if change == 'question':
        rules['questions']['effectiveness-q2']['checks'][0]['text'] = '다른 관측 사실을 추출해야 한다.'
    elif change == 'state':
        rules['states']['substantial'] = 0.8
    elif change == 'system':
        system += ' 새로운 추출 조건을 적용한다.'
    elif change == 'schema':
        original = schema
        def schema(*args):
            result = original(*args)
            result['properties']['evidence']['items']['properties']['finding']['maxLength'] = 1100
            return result
    elif change == 'implementation':
        implementation = 'changed-extraction-implementation'
    elif change == 'window':
        window += 1
    elif change == 'unknown_release':
        rules['version'] = 'unknown-future-release'
    elif change == 'text':
        from pathlib import Path
        Path(doc['extracted_path']).write_text('추가된 다른 실적 원문', encoding='utf-8')
    elif change == 'model':
        model = 'google/gemini-3.5-flash-lite'
    elif change == 'source':
        doc['sha256'] = 'replacement-source-with-same-text'
    elif change == 'artifact':
        doc['artifact'] = True
    with patch.object(review, 'RULES', rules), patch.object(review, 'EXTRACTION_SYSTEM_PROMPT', system), \
         patch.object(review, 'extraction_schema', schema), patch.object(review, 'CHUNK_SIZE', window), \
         patch.object(review, '_extraction_implementation_digest', return_value=implementation), \
         patch.object(review, 'connection'), llm_model_context(model), \
         patch.object(review, '_request_json', return_value=({'evidence': []}, 'synthetic')) as request:
        result = review.analyze_document(doc)
    assert request.call_count == 1
    assert result['status'] == 'completed'
    assert result['chunks'][0]['evidence'] == []  # Old facts were not silently reused.


def test_wider_scope_reuses_legacy_window_and_extracts_only_new_span(tmp_path):
    qid = 'effectiveness-q2'
    doc = legacy_document(tmp_path, scopes={qid: {'mode': 'focused', 'ranges': [[0, 15]]}})
    text = doc['scope_text']
    doc['question_scopes'] = {qid: {'mode': 'focused', 'ranges': [[0, len(text)]]}}
    with patch.object(review, 'connection'), llm_model_context(MODEL), \
         patch.object(review, '_request_json', return_value=({'evidence': []}, 'synthetic')) as request:
        result = review.analyze_document(doc)
    assert request.call_count == 1
    payload = json.loads(request.call_args.args[1])
    assert (payload['chunk_start'], payload['chunk_end']) == (15, len(text))
    assert result['chunks'][0] == doc['dac_fulltext_cache']['chunks'][0]
    assert result['rubric_digest'] == LEGACY_RULE
    assert result['scoring_rubric_digest'] == review.RULE_DIGEST


def test_bridge_is_pinned_to_actual_extraction_code_and_semantics():
    assert review.extraction_contract_digest() == review.AUDITED_EXTRACTION_CONTRACT
    assert review.extraction_rule_digest() == LEGACY_RULE
    # Score thresholds do not participate in fact extraction. The current
    # judgment digest does; its independent invalidation is tested separately.
    with patch.object(review, 'RULES', {**review.RULES, 'coverage_min': 0.99}):
        assert review.extraction_rule_digest() == LEGACY_RULE
