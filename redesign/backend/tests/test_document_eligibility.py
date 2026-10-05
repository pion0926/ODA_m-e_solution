"""Archive/exclusion safeguards and source isolation, without paid AI calls."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from kodame_intake.document_eligibility import text_fingerprint, validate_screening, duplicate, filter_performance_model, screen_with_repair
from kodame_intake.intake_triage import classify
from kodame_intake.api.intake_routes import set_evaluation_scope
from kodame_intake.api.schemas import EvaluationScopeRequest
from kodame_intake.admin import mutation_menu_permission

TEXT = '사업설계매트릭스(PDM) 영향 성과 산출물 객관적 검증지표 검증수단 가정'
CONTEXT = [{'id':'pdm','role':'pdm','file_name':'선택한 PDM.pdf'}]


def decision(**changes):
    return {'excluded':True,'code':'alternate_pdm','confidence':.98,'reason':'별도 기준 PDM이 등록됨',
            'reference_id':'pdm','document_purpose':'pdm_design','evidence_quote':TEXT,
            'explicit_replacement':False,**changes}


def test_whitespace_identity_does_not_merge_different_numbers():
    text = TEXT*10 + '목표 10명'
    assert text_fingerprint(text) == text_fingerprint(' \n'.join(text))
    assert text_fingerprint(text) != text_fingerprint(text.replace('10명','12명'))
    assert text_fingerprint('자료없음') is None


@pytest.mark.parametrize('change',[
    {'confidence':.5}, {'evidence_quote':'원문에 존재하지 않는 PDM 문장'},
    {'reference_id':'unknown'}, {'document_purpose':'performance'}, {'document_purpose':'change_history'},
    {'code':'superseded','explicit_replacement':False},
    {'code':'unrelated','document_purpose':'performance'}])
def test_uncertain_or_ungrounded_exclusion_keeps_document(change):
    assert not validate_screening(decision(**change), TEXT, CONTEXT)['excluded']


def test_standalone_alternate_pdm_excluded_with_verifiable_reference():
    result = validate_screening(decision(), TEXT, CONTEXT)
    assert result['excluded'] and result['reference_name'] == '선택한 PDM.pdf'
    assert not validate_screening(decision(), TEXT, [{'id':'pdm','role':'project_plan','file_name':'계획서'}])['excluded']


def test_triage_combines_scope_without_extra_ai_call():
    with patch('kodame_intake.intake_triage._request_json',return_value=({'kind':'artifact','confidence':.99,'evaluation_scope':decision()},'model')) as request:
        result = classify('old.pdf', TEXT, evaluation_context=CONTEXT)
    assert request.call_count == 1
    assert result['evaluation_scope']['excluded']
    assert '평가' in request.call_args.args[0]


def test_invalid_exclusion_is_rechecked_once_using_real_quote_and_reference():
    raw = decision(evidence_quote='원문에 없는 합쳐 쓴 문장')
    with patch('kodame_intake.openrouter._request_json', return_value=(decision(), 'model')) as request:
        result = screen_with_repair(raw, TEXT, CONTEXT, {})
    assert request.call_count == 1
    assert result['excluded'] and result['validation']['status'] == 'verified'
    assert result['validation']['initial_quote'] == raw['evidence_quote']


@pytest.mark.parametrize('candidate', [decision(excluded=False), decision()])
def test_valid_screening_never_spends_an_extra_request(candidate):
    with patch('kodame_intake.openrouter._request_json') as request:
        result = screen_with_repair(candidate, TEXT, CONTEXT, {})
    request.assert_not_called()
    assert result['excluded'] == candidate['excluded']


def test_recheck_cannot_exclude_without_valid_grounding_or_loop():
    invalid = decision(evidence_quote='원문에 없는 근거')
    with patch('kodame_intake.openrouter._request_json', return_value=(invalid, 'model')) as request:
        result = screen_with_repair(invalid, TEXT, CONTEXT, {})
    assert request.call_count == 1 and not result['excluded']
    assert result['validation']['status'] == 'retained'


def test_scope_repair_ai_failure_preserves_upload_and_evaluation_inclusion():
    from kodame_intake.openrouter import AnalysisError
    with patch('kodame_intake.openrouter._request_json', side_effect=AnalysisError('provider unavailable')):
        result = screen_with_repair(decision(evidence_quote='invalid'), TEXT, CONTEXT, {})
    assert not result['excluded']
    assert result['validation']['status'] == 'repair_unavailable'


def test_foundation_never_auto_excluded_and_duplicate_requires_completed_source():
    conn = MagicMock()
    assert duplicate(conn, {'upload_role':'pdm'}) is None
    conn.execute.assert_not_called()
    conn.execute.return_value.fetchone.return_value = {'id':'canonical','original_name':'stored.pdf'}
    result = duplicate(conn, {'id':'new','queue_position':10,'sha256':'abc','upload_role':'evidence'})
    assert result['code'] == 'duplicate'
    assert "status='completed'" in conn.execute.call_args.args[0]


def test_excluded_measurements_cannot_survive_in_dac_or_incremental_baseline():
    observations = [dict(document_id=doc,kind=kind,value=value,period='2026',quote='근거')
                    for doc,kind,value in [('kept','target','10명'),('kept','actual','6명'),('removed','actual','80명')]]
    original = {'performance_indicators':[{'id':'i','indicator':'강사 수','target':'10명','actual':'80명',
        'measurement_sources':observations,'evidence_document_ids':['kept','removed'],
        'selected_measurements':{'target':observations[0],'actual':observations[2]}, 'risk_analysis':{'text':'80명'}}],
        'monitoring':{'pair_results':{'x':{'document_id':'removed'},'y':{'document_id':'kept'}},
                     'reviewed_mappings':{'i':['removed','kept']}}}
    filtered = filter_performance_model(original, ['kept'])
    item = filtered['performance_indicators'][0]
    assert item['actual'] == '6명' and item['achievement_rate'] == 60
    assert item['risk_analysis'] == {} and item['evidence_document_ids'] == ['kept']
    assert list(filtered['monitoring']['pair_results']) == ['y']
    assert original['performance_indicators'][0]['actual'] == '80명'


@pytest.mark.parametrize('role,status,active,stale',[
    ('pdm','completed',False,False),('evidence','processing',False,False),
    ('evidence','completed',True,False),('evidence','completed',False,True)])
def test_manual_scope_change_respects_foundation_worker_and_workflow_guards(role,status,active,stale):
    stamp = datetime.now(timezone.utc)
    row = {'id':'d','upload_role':role,'status':status,'updated_at':stamp}
    with patch('kodame_intake.api.intake_routes.connection') as connection, \
         patch('kodame_intake.api.intake_routes.lock_project_workflow'), \
         patch('kodame_intake.api.intake_routes.active_workflow_jobs',return_value=['dac'] if active else []):
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = row
        with pytest.raises(HTTPException) as error:
            set_evaluation_scope('d',EvaluationScopeRequest(excluded=True,reason='중복',expected_updated_at='old' if stale else stamp.isoformat()))
        assert error.value.status_code == 409
        assert not any('UPDATE intake_documents' in c.args[0] for c in conn.execute.call_args_list)
    assert mutation_menu_permission('PUT','/api/v2/intake/jobs/d/evaluation-scope') == 'evidence_upload'
