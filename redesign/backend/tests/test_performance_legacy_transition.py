"""Purpose-policy rollout does not erase another project's proven old results."""
import copy
from unittest.mock import patch

from kodame_intake.performance_delta import enrich, fingerprint
from kodame_intake.performance_review import deferred_legacy_pairs, selected_recheck_count
from kodame_intake.performance_targets import TARGET_SELECTION_VERSION
from kodame_intake.pdm_mapping_policy import VERSION


INDICATOR = {'id':'i', 'indicator':'양성 인원 수 (명)','evidence':'결과보고','target':'10명','actual':'4명',
             'evidence_document_ids':['old']}
ROSTER = {**INDICATOR,'text':INDICATOR['indicator'],'mov':INDICATOR['evidence']}


def document(key, version=3):
    return {'id':key,'original_name':key,'sha256':key,'status':'completed','upload_role':'evidence',
            'analysis':{'evidence_matches':{'version':version,'sources':{'pdm':{'id':'p'}},'pdm':[]}}}


def previous():
    observed = {'indicator_id':'i','document_id':'old','file_name':'old','kind':'actual','value':'4명',
                'quote':'실제 양성 4명','period':'2026'}
    item = {**copy.deepcopy(INDICATOR),'measurement_sources':[observed],
            'selected_measurements':{'actual':observed},
            'target_selection':{'version':TARGET_SELECTION_VERSION}}
    record = {'document_id':'old','indicator_id':'i','measurement_version':'pdm-evidence-v7-proposals',
              'observations':[observed],'reviews':[{'indicator_id':'i','status':'found','reason':'확인'}]}
    return {'source_document_id':'p','model':{'performance_indicators':[item],
            'monitoring':{'reviewed_mappings':{'i':['old']},
                         'pair_results':{fingerprint('p',document('old'),INDICATOR):record}}}}


def test_only_previously_reviewed_v3_pairs_are_deferred():
    saved = previous()
    docs = [document('old'),document('unknown-topic')]
    saved['model']['monitoring']['reviewed_mappings']['i'].append('unknown-topic')
    assert VERSION >= 4
    assert deferred_legacy_pairs(docs,[ROSTER],'p',saved) == {'i':['old']}
    assert deferred_legacy_pairs(docs,[ROSTER],'new-pdm',saved) == {}


def test_v4_removed_mapping_and_manual_exclusion_are_not_revived():
    assert deferred_legacy_pairs([document('old',VERSION)],[ROSTER],'p',previous()) == {}
    doc = document('old')
    doc['analysis']['pdm_mapping_overrides'] = {'version':VERSION,'source_document_id':'p',
                                               'included':[],'excluded':['i']}
    assert deferred_legacy_pairs([doc],[ROSTER],'p',previous()) == {}


def test_previous_result_survives_legacy_transition_without_ai_or_restored_mapping():
    saved = previous(); row = copy.deepcopy(INDICATOR); row['evidence_document_ids'] = []
    plan = {'source_document_id':'p','mappings':{'i':[]},'new_mappings':{'i':[]},'deferred_mappings':{'i':['old']}}
    with patch('kodame_intake.pdm_evidence.extract_measurements') as extract:
        result = enrich([row],[document('old')],plan,saved)
    extract.assert_not_called()
    assert row['actual'] == '4명'
    assert row['evidence_document_ids'] == []
    assert row['mapping_review_required'] and row['deferred_purpose_document_ids'] == ['old']
    assert row['measurement_sources'][0]['document_id'] == 'old'
    assert result['pair_results']


def test_new_document_can_update_same_indicator_while_legacy_history_is_preserved():
    saved = previous(); row = copy.deepcopy(INDICATOR); row['evidence_document_ids'] = ['new']
    docs = [document('old'),document('new',VERSION)]
    plan = {'source_document_id':'p','mappings':{'i':['new']},'new_mappings':{'i':['new']},
            'deferred_mappings':{'i':['old']}}
    def extract(doc, indicators, **kwargs):
        assert doc['id'] == 'new'
        doc['analysis']['pdm_measurements'] = {'reviews':[{'indicator_id':'i','status':'found','reason':'실적 확인'}]}
        return [{'indicator_id':'i','document_id':'new','file_name':'new','kind':'actual','value':'6명',
                 'quote':'2026 실제 양성 6명','period':'2026'}]
    with patch('kodame_intake.pdm_evidence.extract_measurements',side_effect=extract) as request:
        enrich([row],docs,plan,saved)
    assert request.call_count == 1 and row['actual'] == '6명'
    assert {item['document_id'] for item in row['measurement_sources'] if item['kind']=='actual'} == {'old','new'}
    assert row['mapping_review_required']


def test_finished_v4_remap_retracts_removed_legacy_actual():
    saved = previous()
    saved['model']['monitoring']['reviewed_mappings'] = {'i':[]}
    saved['model']['monitoring']['deferred_mappings'] = {'i':['old']}
    saved['model']['performance_indicators'][0]['evidence_document_ids'] = []
    row = {**copy.deepcopy(INDICATOR),'evidence_document_ids':[]}
    plan = {'source_document_id':'p','mappings':{'i':[]},'new_mappings':{'i':[]},'deferred_mappings':{},
            'mapping_changed_indicator_ids':['i']}
    with patch('kodame_intake.pdm_evidence.extract_measurements') as request:
        enrich([row],[document('old',VERSION)],plan,saved)
    request.assert_not_called()
    assert row['actual'] == '-' and row['mapping_review_required'] is False


def test_recheck_count_only_includes_current_selected_old_pairs():
    docs = [document(key) for key in ('selected-old','already-valid','new','unmapped-old','deferred-old')]
    row = {**ROSTER,'document_ids':['selected-old','new'],'retained_document_ids':['already-valid'],
           'deferred_document_ids':['deferred-old']}
    keys = {doc['id']:fingerprint('p',doc,ROSTER) for doc in docs}
    old = {keys[key]:{} for key in ('selected-old','already-valid','unmapped-old','deferred-old')}
    reusable = {keys['already-valid']:{}}
    assert selected_recheck_count('p',docs,[row],old,reusable) == 1
