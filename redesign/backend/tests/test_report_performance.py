from copy import deepcopy
from kodame_intake.report_performance import performance_context, achievement_records, bind_achievement, source_ids
from backend.oda_me.hwpx.achievement_records import indexed_achievement_records


def model():
    return {'performance_indicators': [
        {'id':'outcome-1-2','tier_id':'outcome','indicator':'교육과정 승인 여부(유/무)','evidence':'승인 공문',
         'target':'유','actual':'유','measurement_status':'extracted','measurement_sources':[],
         'selected_measurements':{'actual':{'document_id':'approval','quote':'approved','value':'유'}}},
        {'id':'outputs-3-1-1','tier_id':'outputs','indicator':'CPCR 강사 수(명)','evidence':'명단',
         'target':'20명','actual':'6명','achievement_rate':30.0,'measurement_status':'extracted',
         'measurement_sources':[{'kind':'target','document_id':'plan','value':'10명'}],
         'selected_measurements':{'actual':{'document_id':'table','quote':'실적 6명','value':'6명'}}},
        {'id':'outcome-2-1','tier_id':'outcome','indicator':'합격률(%)','target':'-','actual':'-',
         'measurement_status':'conflict','measurement_sources':[]},
    ]}


def test_saved_values_and_qualitative_decision_reach_report_without_mutation():
    saved=model(); before=deepcopy(saved)
    context=performance_context(saved,['approval','plan','table'])
    assert saved==before
    assert context['indicators'][0]['achievement_label']=='충족'
    assert context['indicators'][1]['actual']=='6명'
    assert set(source_ids(context))=={'approval','table'}
    assert context['indicators'][1]['other_target_values']==['10명']


def test_report_cells_cannot_erase_verified_values_or_invent_zero():
    context=performance_context(model(),['approval','plan','table'])
    content=bind_achievement('- [교육 승인]: 성과지표: 승인 / 목표치: 미기재\n\nㅇ 성과 해석\n현재 문헌 기준으로 해석함.',context)
    records=indexed_achievement_records(content)
    assert len(records)==3
    assert '목표치: 유' in records[0] and '종료선: 유' in records[0] and '대비 결과: 충족' in records[0]
    assert '목표치: 20명' in records[1] and '종료선: 6명' in records[1] and '30%' in records[1]
    assert '실적 미확인' in records[2] and '판정 보류' in records[2]
    assert '현재 문헌 기준으로 해석함.' in content


def test_excluded_source_does_not_enter_report():
    saved=model(); row=saved['performance_indicators'][0]
    row['measurement_sources']=[{'document_id':'approval','kind':'actual','value':'유','quote':'approved'}]
    context=performance_context(saved,['plan','table'])
    assert context['indicators'][0]['actual']=='-'
    assert 'approval' not in source_ids(context)


def test_missing_performance_does_not_fabricate_records():
    assert bind_achievement('기존 본문',performance_context({},[]))=='기존 본문'


def test_incomplete_measurements_cannot_be_called_achieved():
    saved=model(); saved['performance_indicators'][0]['measurement_status']='incomplete'
    records=achievement_records(performance_context(saved,['approval','plan','table']))
    assert '분석 미완료로 달성 판정 보류' in records[0]


def test_verified_zero_is_distinct_from_missing():
    context={'indicators':[{'id':'outputs-1-1','tier_id':'outputs','indicator':'횟수',
        'baseline':0,'target':1,'actual':0,'achievement_rate':0,'measurement_status':'extracted'}]}
    record=achievement_records(context)[0]
    assert '기초선: 0' in record and '현재 실적: 0' in record and '대비 결과: 0%' in record
