import json
from unittest.mock import Mock
import pytest
from kodame_intake.measurement_semantics import verify
from kodame_intake.openrouter import AnalysisError
from kodame_intake.performance_delta import reconcile, history
from kodame_intake.pdm_evidence import MEASUREMENT_VERSION


def test_planned_value_rejected_but_reported_value_preserved_with_header_context():
    sources={'S1':'연도별 목표치 2026 2027','S2':'합격률 80 90','S3':'CPCR 강사 목표 10명 실적 6명'}
    observations=[{'kind':'actual','value':'90%','quote':sources['S2']},
                  {'kind':'actual','value':'6명','quote':sources['S3']}]
    request=Mock(return_value=({'decisions':[{'candidate_id':'M0','keep':False,'reason':'목표치'},
                                            {'candidate_id':'M1','keep':True,'reason':'보고 실적'}]},'test'))
    accepted,rejected=verify({'original_name':'사업계획서.pdf'},[],sources,observations,request)
    assert [o['value'] for o in accepted]==['6명']
    assert rejected[0]['exclusion_reason']=='목표치'
    assert json.loads(request.call_args.args[1])['sources'][0]['text']==sources['S1']


def test_ordinary_result_does_not_make_extra_call():
    request=Mock()
    observations=[{'kind':'actual','value':'6명','quote':'실적 6명'}]
    assert verify({'original_name':'실적.xlsx'},[],{},observations,request)==(observations,[])
    request.assert_not_called()


def test_incomplete_verification_is_not_saved_as_negative():
    request=Mock(return_value=({'decisions':[]},'test'))
    with pytest.raises(AnalysisError):
        verify({'original_name':'계획서.pdf'},[],{'S1':'목표 90'},[{'quote':'목표 90'}],request)
    assert request.call_count==2


def test_retracted_actual_is_cleared_without_losing_pdm_target():
    prior={'target':'80%','actual':'90%','measurement_sources':[{'kind':'actual','value':'90%'}]}
    item={**prior}
    reconcile(item,[],[],prior)
    assert item['actual']=='-'
    assert item['target']=='80%'
    assert item['achievement_rate'] is None


def test_only_old_positive_planning_pairs_are_rechecked():
    records={key:{'document_id':key,'measurement_version':version,'observations':observations,
                  'reviews':[{'status':'no_measurement'}]} for key,version,observations in [
        ('old','pdm-evidence-v4-recheck',[{'kind':'actual','value':'90%','quote':'자격시험 80 90'}]),
        ('empty','pdm-evidence-v4-recheck',[]),
        ('new',MEASUREMENT_VERSION,[{'kind':'actual','value':'6명','quote':'실적 6명'}])]}
    documents=[{'id':key,'original_name':'사업계획서.pdf'} for key in records]
    result=history({'source_document_id':'p','model':{'monitoring':{'pair_results':records}}},documents,[],'p')
    assert set(result)=={'empty','new'}
