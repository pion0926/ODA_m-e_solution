import pytest
from kodame_intake.measurement_dimensions import validate_dimension
from kodame_intake.performance_delta import reconcile


@pytest.mark.parametrize('value,quote,expected', [
    ('80','CPCR 강사 양성여부(명) 80 100 - 산출식에 근거',None),
    ('80명','CPCR 강사 양성여부(명) 80 100 - 산출식에 근거',None),
    ('6','CPCR 강사 목표 10명 실적 6명','6명'),
    ('6명','CPCR 강사 목표 10명 실적 6명','6명'),
    ('60%','CPCR 강사 양성 달성률 60%',None),
])
def test_count_is_not_formula_score(value,quote,expected):
    accepted,reason=validate_dimension({'indicator':'CPCR 강사 수 (명)'},{'value':value,'quote':quote})
    assert (accepted or {}).get('value') == expected
    assert bool(reason) == (expected is None)


def test_percent_is_not_number_of_manuals():
    assert validate_dimension({'indicator':'매뉴얼 개발 건수 (건)'},{'value':'100건','quote':'출제 매뉴얼 개발 100%'})[0] is None
    assert validate_dimension({'indicator':'표준 교육과정 승인 여부(유/무)'},{'value':'100%','quote':'교육과정 승인 100%'})[0] is None


def test_damaged_rate_unit_is_not_a_unitless_decimal():
    assert validate_dimension({'indicator':'취업률 (5)'},{'value':'0.7','quote':'C7=0.7'})[0] is None
    assert validate_dimension({'indicator':'취업률 (5)'},{'value':'70%','quote':'목표 70%'})[1] is None


def test_approval_complete_label_requires_approval_context():
    indicator={'indicator':'표준 교육과정 승인 여부(유/무)'}
    assert validate_dimension(indicator,{'value':'완료','quote':'교육과정 승인 완료'})[0]['value']=='유'
    assert validate_dimension(indicator,{'value':'완료','quote':'사업 완료'})[0]['value']=='완료'


def test_valid_actual_survives_ambiguous_formula():
    item={'id':'i','indicator':'CPCR 강사 수 (명)','target':'-','actual':'-'}
    observations=[{'kind':'target','value':'10명','quote':'목표 10명 실적 6명','period':''},
                  {'kind':'actual','value':'6명','quote':'목표 10명 실적 6명','period':''},
                  {'kind':'actual','value':'80','quote':'산출식 80 100','period':'2026'}]
    reconcile(item,observations,[])
    assert item['actual']=='6명'
    assert item['achievement_rate']==60
    assert len(item['excluded_measurements'])==1
