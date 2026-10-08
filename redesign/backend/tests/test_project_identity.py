import json
from copy import deepcopy
from unittest.mock import patch

from kodame_intake.project_identity import (
    plan_title_candidates, resolve_project_identity, project_title_overview, project_title_section,
)
from kodame_intake.foundation_facts import extract_plan_facts


PLAN = '''[PDF 페이지 1]
사 업 계 획 서
(우즈베키스탄 응급구조학과 (Paramedicine) 구축 및
지역사회 CPCR (Cardio Pulmonary Cerebral Resuscitation),
MCI (Mass Casualty Incident) Triage 교육 프로그램
2026. 03.
[PDF 페이지 2]
사 업 내 용 요 약
사업명
국문
 우즈베키스탄 응급구조학과 (Paramedicine) 구축 및 지역사회 CPCR (Cardio
 Pulmonary Cerebral Resuscitation), MCI (Mass Casualty Incident) Triage 교육
 프로그램
영문
English project title
[PDF 페이지 40]
연계 대상 사업
- 사업명: 다른 기관의 응급의료 지원 사업
사업기간 2026년
[PDF 페이지 73]
예산집행계획서 산출 내역
협력대학
응급구조
학과신설
학생인건비 6,360
'''
TITLE = '우즈베키스탄 응급구조학과 구축 및 지역사회 CPCR, MCI Triage 교육 프로그램'


def test_formal_name_preserves_exact_source_span_and_ignores_budget_and_linked_project():
    result = resolve_project_identity(PLAN, '임시 프로젝트')
    assert result['title'] == TITLE
    assert result['source'] == 'project_name_field'
    loc = result['source_location']
    assert PLAN[loc['start']:loc['end']] == result['quote']
    assert loc['page'] == 2


def test_budget_quote_is_never_a_name_and_does_not_fail_entire_intake():
    response = {'facts': [
        {'field': 'project_name', 'value': '학과신설', 'quote': '학과신설'},
        {'field': 'activities', 'value': '응급구조 학과신설', 'quote': '학과신설'},
    ]}
    with patch('kodame_intake.foundation_facts._request_json', return_value=(response, 'mock')):
        result = extract_plan_facts(PLAN)
    assert [f['value'] for f in result['facts'] if f['field'] == 'project_name'] == [TITLE]
    assert any(f['field'] == 'activities' for f in result['facts'])
    assert result['rejected_quotes'] == 1


def test_missing_title_retains_explicit_project_registration_with_provenance():
    assert plan_title_candidates('예산내역\n협력대학\n학과신설\n6,360') == []
    result = resolve_project_identity('예산내역\n학과신설', '르완다 농촌 식수 공급 사업')
    assert result['source'] == 'registered_project'
    assert result['title'] == '르완다 농촌 식수 공급 사업'
    assert resolve_project_identity('', '새 ODA 평가 프로젝트')['source'] == 'unresolved'


def test_conflicting_formal_names_are_not_arbitrarily_selected():
    text = '사업명: 르완다 농촌 식수 공급 사업\n사업기간: 2026\n사업명: 네팔 지역 의료 지원 사업\n사업기간: 2027'
    assert resolve_project_identity(text)['reason'] == 'conflicting_plan_titles'


def test_cover_fallback_excludes_date_and_organization():
    text = PLAN.split('[PDF 페이지 2]')[0] + '[PDF 페이지 2]\n사업기간 2026년'
    identity = resolve_project_identity(text)
    assert identity['source'] == 'plan_cover'
    assert identity['title'] == TITLE
    assert '2026' not in identity['title']


def test_projection_does_not_rewrite_original_analysis_or_other_fields():
    original = {'project_name': {'text': '학과신설: AI가 확장한 제목', 'facts': [{'value': '학과신설'}]},
                'budget': {'text': '100억원'}}
    before = deepcopy(original)
    projection = project_title_overview(original, resolve_project_identity(PLAN))
    assert original == before
    assert projection['project_name']['text'] == TITLE
    assert projection['project_name']['original_ai_text'] == before['project_name']['text']
    assert projection['budget'] == before['budget']


def test_grade_projection_preserves_scores_and_reasons():
    content = json.dumps({'schema': 'section4_grade_slots_v1', 'slots': {
        'project_label': '학과신설: 잘못된 제목', 'overall_score': '10.2/20점',
        'koica_grade': 'E', 'relevance_policy_reason': '실제 작성된 근거'}}, ensure_ascii=False)
    projected = json.loads(project_title_section('grade', content, resolve_project_identity(PLAN)))
    assert projected['slots']['project_label'] == 'ㅇ 평가대상 사업명 : ' + TITLE
    for field in ('overall_score', 'koica_grade', 'relevance_policy_reason'):
        assert projected['slots'][field] == json.loads(content)['slots'][field]
    assert project_title_section('conclusion', content, resolve_project_identity(PLAN)) == content
