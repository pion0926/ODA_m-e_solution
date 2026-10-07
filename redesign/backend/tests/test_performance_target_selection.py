"""Goals are tied to actual reporting scope, never chosen by the largest value."""
import copy
from unittest.mock import patch

from kodame_intake.performance_delta import enrich, fingerprint, reconcile
from kodame_intake.performance_targets import TARGET_SELECTION_VERSION, target_policy_needs_review
from kodame_intake.pdm_evidence import MEASUREMENT_VERSION


def observation(kind, value, document='annual', quote=None, period=''):
    return {'kind':kind, 'value':value, 'document_id':document, 'file_name':document,
            'indicator_id':'i', 'quote':quote or f'현재 목표 10명 실적 6명', 'period':period}


def test_future_high_goal_does_not_retroactively_reduce_current_achievement():
    row = {'id':'i','indicator':'양성 강사 수 (명)','target':'20명','actual':'6명'}
    measured = observation('actual','6명')
    future = observation('target','20명','future','다음 연도 강사 양성 목표 20명')
    target = observation('target','10명')
    reconcile(row,[future,target,measured],[])
    assert row['target'] == '10명' and row['actual'] == '6명'
    assert row['achievement_rate'] == 60
    assert row['target_selection']['basis'] == 'same_actual_source_row'
    assert future in row['measurement_sources']


def test_explicit_pdm_goal_remains_authoritative_over_copresent_report_goal():
    row = {'id':'i','indicator':'강사 수 (명)','target':'12명','actual':'-',
           'pdm_target':{'origin':'pdm_explicit_target','value':'12명','quote':'목표 12명','document_id':'pdm'}}
    reconcile(row,[observation('target','10명'),observation('actual','6명')],[])
    assert row['target'] == '12명' and row['achievement_rate'] == 50
    assert row['target_selection']['basis'] == 'pdm_explicit_target'


def test_same_file_future_goal_is_incompatible_with_actual_period():
    row = {'id':'i','indicator':'강사 수 (명)','target':'-','actual':'-'}
    actual = observation('actual','6명',period='2026')
    current = observation('target','10명',period='2026')
    future = observation('target','20명',period='2027')
    reconcile(row,[future,current,actual],[])
    assert row['target'] == '10명' and row['achievement_rate'] == 60


def test_same_source_with_unresolved_conflicting_goals_is_not_maximized():
    row = {'id':'i','indicator':'강사 수 (명)','target':'20명','actual':'6명'}
    quote = '목표10명 변경안20명 실적6명'
    reconcile(row,[observation('target','10명',quote=quote),observation('target','20명',quote=quote),
                   observation('actual','6명',quote=quote)],[])
    assert row['target'] == '-' and row['actual'] == '6명'
    assert row['achievement_rate'] is None and row['measurement_status'] == 'conflict'


def test_without_actual_conflicting_reference_goals_remain_pending():
    row = {'id':'i','indicator':'시험 합격률(%)','target':'95% 이상','actual':'-'}
    sources = [observation('target','80%','old','합격 목표 80%'),
               observation('target','95% 이상','future','합격 목표 95% 이상')]
    reconcile(row,sources,[])
    assert row['target'] == '-' and row['achievement_rate'] is None
    assert row['target_selection']['status'] == 'review_required'
    assert [item['value'] for item in row['measurement_sources']] == ['80%','95% 이상']


def test_single_inequality_goal_preserves_operator_without_invented_ratio():
    row = {'id':'i','indicator':'시험 합격률(%)','target':'-','actual':'-'}
    quote = '합격 목표 95% 이상, 실제 합격률 96%'
    reconcile(row,[observation('target','95% 이상',quote=quote),observation('actual','96%',quote=quote)],[])
    assert row['target'] == '95% 이상' and row['actual'] == '96%'
    assert row['measurement_status'] == 'extracted' and row['achievement_rate'] is None


def test_same_value_from_several_reference_documents_is_consensus():
    row = {'id':'i','indicator':'시험 합격률(%)','target':'-','actual':'-'}
    reconcile(row,[observation('target','80%','a','목표 80%'),observation('target','80.0%','b','목표 80.0%')],[])
    assert row['target'] == '80%' and row['measurement_status'] == 'extracted'


def test_target_policy_refresh_reuses_committed_measurements_without_paid_reanalysis():
    indicator = {'id':'i','indicator':'양성 강사 수 (명)','evidence':'실적표','target':'20명','actual':'6명',
                 'evidence_document_ids':['annual']}
    observations = [observation('actual','6명'),observation('target','10명'),
                    observation('target','20명','future','다음 연도 양성 목표20명')]
    previous_item = {**indicator,'measurement_sources':observations,
                     'selected_measurements':{'actual':observations[0],'target':observations[-1]}}
    documents = [{'id':'annual','original_name':'실적표','sha256':'a'},
                 {'id':'future','original_name':'계획서','sha256':'f'}]
    records = {fingerprint('p',documents[0],indicator):{'document_id':'annual','indicator_id':'i',
               'measurement_version':MEASUREMENT_VERSION,'observations':observations[:2],'reviews':[]}}
    previous = {'source_document_id':'p','model':{'performance_indicators':[previous_item],
                'monitoring':{'pair_results':records,'reviewed_mappings':{'i':['annual']}}}}
    plan = {'source_document_id':'p','mappings':{'i':['annual']},'new_mappings':{'i':[]}}
    row = copy.deepcopy(indicator)
    assert target_policy_needs_review(previous_item)
    with patch('kodame_intake.pdm_evidence.extract_measurements') as extract:
        result = enrich([row],documents,plan,previous)
    extract.assert_not_called()
    assert result['new_pair_count'] == 0 and result['changed_indicator_ids'] == ['i']
    assert row['target'] == '10명' and row['achievement_rate'] == 60
    assert row['target_selection']['version'] == TARGET_SELECTION_VERSION
    assert not target_policy_needs_review(row)
    # Rebuilding the roster must not lose a freshly recovered official PDM goal
    # merely because the old model stored a different reported target.
    row = {**copy.deepcopy(indicator), 'pdm_target':{'origin':'pdm_explicit_target','value':'12명',
                                                    'quote':'공식 목표 12명','document_id':'p'}}
    with patch('kodame_intake.pdm_evidence.extract_measurements') as extract:
        enrich([row],documents,plan,previous)
    extract.assert_not_called()
    assert row['target'] == '12명' and row['achievement_rate'] == 50
