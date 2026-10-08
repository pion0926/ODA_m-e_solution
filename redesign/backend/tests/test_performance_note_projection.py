"""Export translates a known internal label without changing measurement facts."""
import pytest

from backend.oda_me.hwpx.performance_notes import readable_performance_notes
from kodame_intake.hwpx_pipeline import normalize_section_text


RAW = "actual: 기준일 미기재, 동일단위 수치 우선 비교"
LABEL = "실적 선택 기준: 기준일이 없어 같은 단위의 수치를 우선 비교함"


@pytest.mark.parametrize("separator", [";", "; ", ";\n"])
def test_known_note_keeps_figures_sources_and_selection_meaning(separator):
    lead = "저장된 성과지표 분석결과를 반영함; 실적 6명 / 목표 10명, 출처: 교육 결과보고서"
    raw = lead + separator + RAW
    assert readable_performance_notes(raw) == lead + separator + LABEL
    assert readable_performance_notes(readable_performance_notes(raw)) == lead + separator + LABEL
    assert raw.endswith(RAW)


@pytest.mark.parametrize("raw", [
    '원문 인용: "' + RAW + '"',
    '> ' + RAW,
    '`' + RAW + '`',
    'actual: 실적 6명, 목표 10명',
    'actual: 기준일 미기재, 다른 선택 규칙',
    RAW + '에 대한 새로운 설명',
    '기타 actual: 기준일 미기재, 동일단위 수치 우선 비교',
])
def test_unknown_notes_and_quoted_text_are_unchanged(raw):
    assert readable_performance_notes(raw) == raw


def test_only_achievement_export_projects_note_and_preserves_table_facts():
    raw = '| 지표 | 실적 | 근거 |\n| --- | --- | --- |\n| 교육 | 6명 | 저장된 결과; ' + RAW + ' |'
    projected, _ = normalize_section_text('achievement', raw)
    other, _ = normalize_section_text('criteria-effectiveness', raw)
    assert LABEL in projected
    assert '6명' in projected
    assert RAW in other
    assert RAW in raw


def test_spaced_unit_note_preserves_the_following_target_selection_field():
    raw = '저장된 결과; actual: 기준일 미기재, 동일 단위 수치 우선 비교 · 목표: 2028년 10명'
    assert readable_performance_notes(raw) == '저장된 결과; ' + LABEL + ' · 목표: 2028년 10명'
