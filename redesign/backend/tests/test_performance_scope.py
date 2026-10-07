"""Incremental evidence never equates document count with completed output count."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kodame_intake.performance_delta import enrich, fingerprint, history, reconcile, comparison_baseline
from kodame_intake.performance_scope import normalize_scope
from kodame_intake.performance_targets import reference_targets
from kodame_intake.pdm_evidence import MEASUREMENT_VERSION, extract_measurements
from kodame_intake.performance_review import validate_selection


INDICATOR = {'id':'training', 'indicator':'유관기관 합동훈련 횟수 (회)', 'evidence':'개최 결과',
             'target':'3회', 'actual':'-', 'evidence_document_ids':[]}


def event(document, day='2026-08-04', name='합동 재난훈련', location='중앙 훈련장', end=None):
    quote = f'{day} {name}을 {location}에서 완료했다.'
    if end:
        quote += f' 종료일 {end}.'
    raw = {'basis':'individual_event','scope_label':'','event_name':name,'event_location':location,
           'event_date':day,'event_end_date':end or day,'event_completed':True}
    scope = normalize_scope(raw, quote, INDICATOR, '1회', 'actual')
    return {'indicator_id':'training','document_id':document,'file_name':document,'kind':'actual',
            'value':'1회','quote':quote,'period':day,'measurement_scope':scope,
            'role_verification':'measurement-role-v2-scope'}


def test_two_reports_for_same_completed_event_count_once():
    row = copy.deepcopy(INDICATOR)
    reconcile(row, [event('report'), event('travel')], [])
    assert row['actual'] == '1회'
    assert row['achievement_rate'] == 33.3
    assert row['selected_measurements']['actual']['supporting_document_ids'] == ['report', 'travel']


def test_new_distinct_event_increments_previous_event_without_recounting_documents():
    row = copy.deepcopy(INDICATOR)
    reconcile(row, [event('old'), event('duplicate'), event('new','2026-09-09')], [])
    assert row['actual'] == '2회'
    assert row['selected_measurements']['actual']['event_dates'] == ['2026-08-04','2026-09-09']


def test_same_day_different_titles_are_not_claimed_as_distinct_events():
    row = copy.deepcopy(INDICATOR)
    reconcile(row, [event('a'), event('b', name='오후 합동 재난훈련')], [])
    assert row['actual'] == '1회'
    assert '별개 행사인지' in row['note']


def test_multiday_event_and_its_last_day_report_are_not_counted_twice():
    row = copy.deepcopy(INDICATOR)
    reconcile(row, [event('a', end='2026-08-06'), event('b','2026-08-06')], [])
    assert row['actual'] == '1회'


def test_monthly_indicator_does_not_sum_previous_month_into_latest_month():
    row = {**copy.deepcopy(INDICATOR), 'indicator':'월별 합동훈련 횟수 (회)'}
    reconcile(row, [event('a'), event('b','2026-08-09'), event('c','2026-09-09')], [])
    assert row['actual'] == '1회'
    assert row['selected_measurements']['actual']['aggregation_window'] == '2026-09'


def test_single_event_cannot_overwrite_previous_cumulative_total():
    row = {**copy.deepcopy(INDICATOR), 'actual':'6회'}
    total = {**event('summary','2026-07-01'),'value':'6회',
             'measurement_scope':{'basis':'cumulative','scope_label':''}}
    reconcile(row, [total, event('new')], [])
    assert row['actual'] == '6회'
    assert row['measurement_status'] == 'conflict'
    assert row['achievement_rate'] is None


@pytest.mark.parametrize('previous', ['-', '0회', '2회'])
def test_verified_cumulative_value_is_shown_even_without_a_correct_prior(previous):
    row = {**copy.deepcopy(INDICATOR), 'actual':previous}
    total = {**event('summary','2026-07-01'), 'value':'10회','quote':'2026-07-01까지 누적 10회 완료',
             'measurement_scope':{'basis':'cumulative','scope_label':''}}
    reconcile(row, [total, event('new')], [])
    assert row['actual'] == '10회'
    assert row['measurement_status'] == 'conflict'
    assert row['aggregation_review_required'] is True
    assert row['achievement_rate'] is None
    assert '포함 여부' in row['note']


def test_mixed_scope_cumulative_baseline_still_uses_latest_then_highest_policy():
    row = {**copy.deepcopy(INDICATOR), 'actual':'2회'}
    def total(document, value, day):
        return {**event(document,day), 'value':value,'quote':f'{day} 누적 {value} 완료',
                'measurement_scope':{'basis':'cumulative','scope_label':''}}
    reconcile(row, [total('old','20회','2026-06-01'), total('new','10회','2026-07-01'),
                    total('same_day','12회','2026-07-01'), event('event')], [])
    assert row['actual'] == '12회' and row['achievement_rate'] is None


def test_unproven_legacy_cumulative_value_does_not_replace_prior_during_scope_conflict():
    row = {**copy.deepcopy(INDICATOR), 'actual':'2회'}
    total = {**event('summary','2026-07-01'), 'value':'10회','quote':'','previous_result':True,
             'measurement_scope':{'basis':'cumulative','scope_label':''}}
    reconcile(row, [total,event('new')], [])
    assert row['actual'] == '2회' and row['achievement_rate'] is None


def test_distinct_population_totals_are_not_compared_as_same_scope():
    row = {'indicator':'양성 강사 수 (명)', 'target':'10명','actual':'3명'}
    observations = [{'kind':'actual','value':value,'period':'2026','quote':value,
                     'measurement_scope':{'basis':'cumulative','scope_label':label}}
                    for value,label in [('4명','기관 A'),('6명','기관 B')]]
    reconcile(row, observations, [])
    assert row['actual'] == '3명' and row['measurement_status'] == 'conflict'


def test_new_monthly_total_does_not_replace_annual_total():
    row = {**copy.deepcopy(INDICATOR), 'actual':'20회'}
    values = [{**event('annual','2026-01-01'), 'value':'20회',
               'measurement_scope':{'basis':'period_total','period_unit':'year'}},
              {**event('monthly','2026-09-01'), 'value':'2회',
               'measurement_scope':{'basis':'period_total','period_unit':'month'}}]
    reconcile(row, values, [])
    assert row['actual'] == '20회' and row['measurement_status'] == 'conflict'


@pytest.mark.parametrize('changes', [{'event_completed':False}, {'event_date':'2026-12-01'},
                                   {'event_name':'없는 행사'}, {'event_location':''}])
def test_ungrounded_event_identity_does_not_enable_counting(changes):
    observed = event('a')
    scope = normalize_scope({**observed['measurement_scope'],**changes}, observed['quote'],INDICATOR,'1회','actual')
    assert scope['basis'] == 'unspecified' and not scope.get('event_identity')


def test_event_without_independent_completion_verification_is_not_aggregated():
    observed = event('a'); observed.pop('role_verification')
    row = copy.deepcopy(INDICATOR)
    reconcile(row,[observed],[])
    assert row['actual'] == '-' and row['measurement_status'] == 'conflict'


def test_v8_rechecks_only_count_pairs_and_retains_valid_other_measurements():
    docs = [{'id':key,'original_name':key} for key in ('count','ratio','approval','empty')]
    indicators = [{'id':'count','text':'양성 수 (명)'},{'id':'ratio','text':'합격률(%)'},
                  {'id':'approval','text':'승인 여부(유/무)'},{'id':'empty','text':'훈련 횟수 (회)'}]
    records = {key:{'document_id':key,'indicator_id':key,'measurement_version':'pdm-evidence-v7-proposals',
                    'observations':[] if key=='empty' else [{'kind':'actual','value':value,'quote':value}],
                    'reviews':[{'status':'no_measurement'}]}
               for key,value in [('count','6명'),('ratio','60%'),('approval','유'),('empty','')]}
    result = history({'source_document_id':'p','model':{'monitoring':{'pair_results':records}}},docs,indicators,'p')
    assert set(result) == {'ratio','approval'}


def test_removed_mapping_reconciles_without_new_paid_calls_and_preserves_target_reference():
    docs = [{'id':'plan','original_name':'계획.txt','sha256':'a'}, {'id':'result','original_name':'보고.txt','sha256':'b'}]
    target = {'indicator_id':'training','document_id':'plan','file_name':'계획.txt','kind':'target','value':'3회',
              'period':'2026','quote':'합동훈련 목표 3회'}
    actual = event('result')
    prior_item = {**INDICATOR,'actual':'1회','evidence_document_ids':['plan','result'],
                  'measurement_sources':[target,actual], 'selected_measurements':{'target':target,'actual':actual}}
    records = {fingerprint('p',doc,INDICATOR):{'document_id':doc['id'],'indicator_id':'training',
                 'measurement_version':MEASUREMENT_VERSION,'observations':[target if doc['id']=='plan' else actual],
                 'reviews':[]} for doc in docs}
    previous = {'source_document_id':'p','model':{'performance_indicators':[prior_item],
                'monitoring':{'pair_results':records,'reviewed_mappings':{'training':['plan','result']}}}}
    plan = {'source_document_id':'p','mappings':{'training':[]},'new_mappings':{'training':[]},
            'mapping_changed_indicator_ids':['training']}
    row = copy.deepcopy(INDICATOR)
    with patch('kodame_intake.pdm_evidence.extract_measurements') as extract:
        result = enrich([row],docs,plan,previous)
    extract.assert_not_called()
    assert row['actual'] == '-' and row['target'] == '3회'
    assert row['target_reference_sources'][0]['document_id'] == 'plan'
    assert row['target_review_required'] is True
    assert result['changed_indicator_ids'] == ['training']


def test_new_target_fact_is_recovered_without_mapping_plan_as_actual(tmp_path):
    path = tmp_path / 'plan.txt'; path.write_text('합동훈련 목표 3회',encoding='utf-8')
    fact = {'id':'f','kind':'target','pdm_indicator_ids':['training'],'verification':'source_quote_verified',
            'scope':'full_text','value':'3','unit':'회','evidence_quote':'합동훈련 목표 3회','period':'2026'}
    document = {'id':'plan','original_name':'계획','extracted_path':str(path),
                'analysis':{'registration_facts':{'facts':[fact]}}}
    result = reference_targets([document],INDICATOR)
    assert result[0]['value'] == '3회' and result[0]['reference_role'] == 'target_definition'
    assert reference_targets([],INDICATOR,{'measurement_sources':result}) == []
    fact['evidence_quote'] = '합동훈련 목표 9회'
    assert reference_targets([document],INDICATOR) == []


def test_mapping_only_change_can_be_explicitly_executed():
    plan = {'ready':True,'revision':'r','message':'','source_document_id':'p','source_file_name':'p',
            'input_snapshot':{},'documents':[], 'indicators':[{'id':'training'}],
            'mapping_changed_indicator_ids':['training']}
    result = validate_selection(plan,'r',{'training':[]})
    assert result['new_mappings'] == {'training':[]}
    assert result['mapping_changed_indicator_ids'] == ['training']


def test_prior_context_omits_repeated_evidence_and_risk_text():
    result = comparison_baseline({'actual':'6명','target':'10명','measurement_sources':[{'quote':'large'}],
                                  'measurement_reviews':[{'reason':'long'}],'risk_analysis':{'text':'long'}})
    assert result == {'actual':'6명','target':'10명'}


@patch('kodame_intake.pdm_evidence.connection')
@patch('kodame_intake.pdm_evidence._request_json')
def test_completed_event_without_literal_one_count_is_verified_then_accepted(request, connection, tmp_path):
    text = '2026-08-04 합동 재난훈련을 중앙 훈련장에서 완료했다. 세 팀이 참여했다.'
    path = tmp_path/'event.txt'; path.write_text(text,encoding='utf-8')
    def respond(system, prompt, title, **kwargs):
        if title == 'KODAME Measurement Role Verification':
            return {'decisions':[{'candidate_id':'M0','keep':True,'reason':'한 행사 실제 완료 확인'}]},'test'
        source = json.loads(prompt)['sources'][0]['source_id']
        return {'observations':[{'indicator_id':'training','kind':'actual','value':'1회','source_id':source,
                                 'context_source_ids':[source],'period':'2026-08-04',
                                 'measurement_scope':event('a')['measurement_scope']}],
                'reviews':[{'indicator_id':'training','status':'found','reason':'개최 완료'}]},'test'
    request.side_effect = respond
    result = extract_measurements({'id':'doc','original_name':'event.txt','extracted_path':str(path)},[INDICATOR])
    assert len(result) == 1 and result[0]['value'] == '1회'
    assert result[0]['role_verification'] == 'measurement-role-v2-scope'
    assert request.call_count == 2
