"""Saved internal diagnoses must not become official grades in a report."""
from copy import deepcopy
import json

from backend.oda_me.reports.context import structured_slots_to_json
from kodame_intake.report_evaluation_context import (
    for_report, is_provisional, qualify_report_text, PROVISIONAL_NOTICE,
)
from kodame_intake.report_generator import (
    _ensure_official_grade_statement, _official_grade_context, _quantitative_consistency_issues,
)
from kodame_intake.hwpx_pipeline import prepare_hwpx_sections


def evaluations(held=False):
    return [{'criterion_id': key, 'criterion_name': key, 'score': None if held and key == 'relevance' else 2.5,
             'question_assessments': [{'question_id': key + '-q1', 'score': 2,
                  'finding': '일부 수행을 확인하였으나 후속 확인이 필요함.',
                  'scoring_trace': {'assessment_basis': 'provisional_document_review'},
                  'evidence_quotes': [{'document_id': 'd1', 'quote': '검토한 원문'}]}]}
            for key in ('relevance', 'coherence', 'effectiveness', 'efficiency', 'sustainability')]


def test_report_prompt_preserves_policy_and_trace_without_mutating_evaluation():
    rows = evaluations(); before = deepcopy(rows)
    projected = for_report(rows)
    assert rows == before
    assert all(row['report_assessment_basis'] == 'provisional_document_review' for row in projected)
    assert '공식 확정평가를 의미하지 않음' in projected[0]['report_assessment_notice']
    assert projected[0]['question_assessments'][0]['score'] == 2
    assert 'evidence_quotes' not in projected[0]['question_assessments'][0]
    assert _official_grade_context(rows)['total_score'] == 12.5
    assert _official_grade_context(rows)['assessment_basis'] == 'provisional_document_review'


def test_saved_grade_slots_keep_numbers_but_mark_provisional_through_hwpx_preparation():
    text = structured_slots_to_json('grade', {'overall_score': '1/20점', 'koica_grade': 'A'})
    result = _ensure_official_grade_statement('grade', text, evaluations())
    prepared, _ = prepare_hwpx_sections({}, {'grade': result}, [], selected_parts={'grade'})
    slots = json.loads(prepared['grade'])['slots']
    assert slots['overall_score'] == '12.5/20점 (잠정)'
    assert slots['koica_grade'].endswith(' (잠정)')
    assert slots['government_grade'].endswith(' (잠정)')
    assert slots['relevance_policy_score'] == '2점'
    assert slots['relevance_total_score'] == '2.5점'


def test_conclusion_cannot_claim_official_confirmation_and_note_is_idempotent():
    result = _ensure_official_grade_statement('conclusion', '공식 종합판정은 12.5/20점임.', evaluations())
    assert '공식 종합판정' not in result
    assert '12.5/20점' in result
    assert PROVISIONAL_NOTICE in result
    assert qualify_report_text('conclusion', result, evaluations()) == result
    assert PROVISIONAL_NOTICE in _ensure_official_grade_statement('criteria-relevance', '실행이 확인됨.', evaluations())


def test_provisional_status_does_not_disable_saved_score_and_grade_validation():
    rows = evaluations()
    result = _ensure_official_grade_statement('conclusion', '내부 잠정 진단임.', rows)
    assert _quantitative_consistency_issues('conclusion', result, rows) == []
    missing = _quantitative_consistency_issues('conclusion', '내부 잠정 진단임.', rows)
    assert any('12.5/20점' in issue for issue in missing)
    assert any('KOICA' in issue for issue in missing)
    assert all('공식' not in issue for issue in missing)
    incorrect = result.replace('12.5/20점', '18/20점')
    assert any('불일치' in issue for issue in _quantitative_consistency_issues('conclusion', incorrect, rows))


def test_held_total_remains_held_and_never_becomes_zero_or_guaranteed_score():
    result = _ensure_official_grade_statement('grade', structured_slots_to_json('grade', {'project_label': '합성 사업'}), evaluations(held=True))
    slots = json.loads(result)['slots']
    assert slots['overall_score'] == slots['koica_grade'] == slots['government_grade'] == '판정보류'
    assert slots['relevance_total_score'] == '판정보류'
    assert slots['coherence_total_score'] == '2.5점'


def test_unrelated_text_and_existing_assessment_policy_are_preserved():
    assert not is_provisional([{'question_assessments': [{'scoring_trace': {}}]}])
    assert qualify_report_text('conclusion', '저장된 기존 본문', []) == '저장된 기존 본문'
    assert qualify_report_text('pdm', '설계 원문', evaluations()) == '설계 원문'
