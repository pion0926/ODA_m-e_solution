import pytest
from kodame_intake.performance_status import apply_categorical_status


@pytest.mark.parametrize('actual,status,label',[('유','ok','충족'),('무','under','미충족')])
def test_binary_result_is_recognized_without_numeric_percentage(actual,status,label):
    item={'indicator':'표준 승인 여부 (유/무)','target':'유','actual':actual,'measurement_status':'extracted','status':'unset'}
    apply_categorical_status(item)
    assert item['status']==status
    assert item['achievement_label']==label
    assert item['achievement_rate'] is None


@pytest.mark.parametrize('state',['incomplete','conflict','no_measurement'])
def test_uncertain_binary_result_is_not_marked_fulfilled(state):
    item={'indicator':'표준 승인 여부 (유/무)','target':'유','actual':'유','measurement_status':state,'status':'unset'}
    apply_categorical_status(item)
    assert item['status']=='unset'
    assert 'achievement_label' not in item
