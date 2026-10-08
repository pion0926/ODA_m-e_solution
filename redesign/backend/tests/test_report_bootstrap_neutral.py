import pytest
from kodame_intake import report_sections


@pytest.mark.parametrize('name,country', [('관개용수 개선','가나'), ('전자정부 민원','라오스'), ('모자보건','네팔')])
def test_initial_report_never_invents_sample_project_facts(monkeypatch, name, country):
    overview = {k:{'text':v} for k,v in {'project_name':name,'country':country,
        'objective':'사업별 목적', 'activities':'사업별 활동', 'outputs':'계획 산출물',
        'outcomes':'계획 성과'}.items()}
    monkeypatch.setattr(report_sections, '_latest_context', lambda:(overview,[],None))
    result = report_sections.bootstrap_contents()
    assert len(result) == 27
    assert name in result['cover'] and country in result['project-overview']
    for prohibited in ['우즈베키스탄','응급구조학과','Job-Code','졸업생','전반적으로 달성']:
        assert prohibited not in '\n'.join(result.values())
    assert '판정보류' in result['conclusion']
    assert '계획 산출물' not in result['pdm']  # PDM must not be filled from plan overview


def test_empty_project_remains_empty(monkeypatch):
    monkeypatch.setattr(report_sections, '_latest_context', lambda:({},[],None))
    assert not any(report_sections.bootstrap_contents().values())
