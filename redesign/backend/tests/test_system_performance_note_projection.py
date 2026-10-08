"""Only canonical system review notes are omitted from final HWPX output."""
from copy import deepcopy
from html import escape
from io import BytesIO
from pathlib import Path
import re
import zipfile

import pytest

from backend.oda_me.hwpx.patchers import (
    ACHIEVEMENT_CELL_OFFSETS, achievement_export_fields, achievement_item_fields,
    find_hwpx_table_span_by_text, find_hwpx_tag_spans, get_hwpx_xml_scope_text,
    parse_achievement_items, patch_hwpx_achievement_table_xml,
    set_hwpx_table_cell_text_xml,
)
from kodame_intake.hwpx_adapters.sections.section14_achievement import ADAPTER
from kodame_intake.hwpx_layout.achievement_readability import improve_achievement_readability
from kodame_intake.hwpx_layout.overflow import resolve_detail_text
from kodame_intake.hwpx_layout.tables import style_achievement_table_xml
from kodame_intake.hwpx_pipeline import prepare_hwpx_sections

MARKER = '저장된 성과지표 분석 결과를 반영함'


def record(note, ident='outputs-3-1'):
    return (f'- [{ident}]: 성과지표: 합성 교육 인원 / 기초선: 0명 / 목표치: 12명'
            f' / 종료선 또는 현재 실적: 7명 / 대비 결과: 58.3% / 지표입증수단(MOV): 출석부 / 비고: {note}')


def template():
    path = Path(__file__).resolve().parents[3] / 'samples' / '5-1. 종료평가 결과보고서 placeholder.hwpx'
    with zipfile.ZipFile(path) as archive:
        return archive.read('Contents/section5.xml').decode('utf-8')


def paragraph(text):
    return '<hp:p id="1" paraPrIDRef="92" pageBreak="0"><hp:run><hp:t>' + escape(text) + '</hp:t></hp:run></hp:p>'


@pytest.mark.parametrize('note', [MARKER, MARKER + '; 근거 자료 검토 이력; 다른 자료의 목표 2030년 30명'])
def test_system_note_is_export_only_and_all_other_fields_are_preserved(note):
    raw = record(note)
    item = parse_achievement_items(raw)[0]
    original = achievement_item_fields(item, 0)
    projected = achievement_export_fields(item, 0)
    assert original['note'] == note
    assert projected['note'] == '' and projected['_system_note_omitted'] is True
    assert {k: v for k, v in projected.items() if k not in {'note', '_system_note_omitted'}} == {
        k: v for k, v in original.items() if k != 'note'}
    assert raw.endswith(note) and achievement_item_fields(item, 0) == original


@pytest.mark.parametrize('note', [
    '사용자 확인: ' + MARKER + '; 직접 작성한 해설',
    '"' + MARKER + '"라는 표현을 검토함',
    MARKER + '이란 문구를 포함한 외부 문서임',
    '저장된 성과지표 분석결과를 반영함; 유사 표현은 자동 삭제하지 않음',
    '2029년 목표는 20명; 목표: 별도 범위를 검토함',
])
def test_manual_and_quoted_notes_are_not_omitted(note):
    item = parse_achievement_items(record(note))[0]
    assert achievement_export_fields(item, 0) == achievement_item_fields(item, 0)


def test_legacy_or_incomplete_canonical_record_with_marker_is_not_omitted():
    item = '지표 ID: outputs-3-1\n성과지표: 교육\n목표치: 12명\n실적 (현재시점): 7명\n비고: ' + MARKER
    assert achievement_export_fields(item, 0) == achievement_item_fields(item, 0)


def test_table_keeps_empty_note_column_and_does_not_create_system_details():
    raw = record(MARKER + '; ' + '내부 검토 이력과 대안 목표 30명. ' * 120)
    patched = patch_hwpx_achievement_table_xml(template(), {'achievement': raw})
    table = find_hwpx_table_span_by_text(patched, ['성과지표', '기초선', '달성도'], 20)[2]
    cells = [get_hwpx_xml_scope_text(table[a:b]) for a,b in find_hwpx_tag_spans(table, 'hp:tc')]
    assert cells[20 + ACHIEVEMENT_CELL_OFFSETS['note']] == ''
    assert cells[20 + ACHIEVEMENT_CELL_OFFSETS['target']] == '12명'
    assert cells[20 + ACHIEVEMENT_CELL_OFFSETS['endline']] == '7명'
    assert '비고' in get_hwpx_xml_scope_text(table)
    styled, _ = style_achievement_table_xml(patched)
    assert MARKER not in styled and '성과지표 상세 S' not in styled


def test_long_manual_note_still_has_lossless_overflow():
    note = '사용자 검토 내용; ' + '2029년 30명은 다른 지역의 목표이며 현재 실적이 아님. ' * 160
    raw = record(note)
    patched = patch_hwpx_achievement_table_xml(template(), {'achievement': raw})
    styled, _ = style_achievement_table_xml(patched)
    refs = set(re.findall(r'\[S\d+ 상세\]', get_hwpx_xml_scope_text(styled)))
    compact = lambda text: re.sub(r'\s+', '', text)
    assert refs
    assert compact(note) in {compact(resolve_detail_text(styled, ref)) for ref in refs}


def test_internal_narrative_records_and_empty_group_header_are_removed_only_from_output():
    raw = record(MARKER + '; 내부 검토 이력')
    xml = paragraph('2. 성과지표별 목표 대비 실적 분석') + paragraph(raw) + paragraph('3. 종합 평가 및 시사점') + paragraph('검토된 성과는 유지함.')
    projected, _ = improve_achievement_readability(xml)
    visible = get_hwpx_xml_scope_text(projected)
    assert MARKER not in visible and '주요 진척과 확인 과제' not in visible
    assert '2. 성과' not in visible and '3. 종합 평가 및 시사점' in visible
    assert '검토된 성과는 유지함.' in visible and MARKER in xml
    assert improve_achievement_readability(projected) == (projected, 0)


def test_mixed_manual_notes_keep_their_group_and_prose():
    raw = paragraph(record(MARKER + '; 내부 설명')) + paragraph(record('직접 확인한 사용 기록을 추가함', 'outputs-4-1'))
    projected, _ = improve_achievement_readability(raw)
    assert MARKER not in projected
    assert '산출물(Output)의 주요 진척과 확인 과제' in projected
    assert '직접 확인한 사용 기록을 추가함' in projected


FALLBACK = ('ㅇ 저장된 목표·실적과 남은 근거 공백을 구분하여 해석함. 기준일 또는 자료 범위가 다른 목표는 '
            '단순 합산하지 않으며, 미확인 실적은 0으로 간주하지 않음.')


def test_exact_system_interpretation_fallback_and_its_empty_heading_are_omitted():
    xml = (paragraph(record(MARKER + '; 내부 메모')) + paragraph('3. 종합 평가 및 시사점')
           + paragraph(FALLBACK))
    projected, _ = improve_achievement_readability(xml)
    assert FALLBACK not in projected and '3. 종합 평가 및 시사점' not in projected
    assert FALLBACK in xml
    assert improve_achievement_readability(projected) == (projected, 0)


@pytest.mark.parametrize('authored', [
    'ㅇ 교육 수료자 7명의 현장 활동이 확인되었으며 후속 운영 기록의 확보가 필요함.',
    FALLBACK + ' 이 사업에서는 지역별 목표 기간을 재검토할 필요가 있음.',
    FALLBACK.replace('0으로', '실패로'),
    'ㅇ 원문 인용: "' + FALLBACK + '"',
])
def test_authored_conclusion_or_similar_fallback_is_preserved(authored):
    xml = (paragraph(record(MARKER + '; 내부 메모')) + paragraph('3. 종합 평가 및 시사점')
           + paragraph(authored))
    projected, _ = improve_achievement_readability(xml)
    assert '3. 종합 평가 및 시사점' in projected
    assert escape(authored) in projected


def test_additional_authored_conclusion_keeps_heading_while_exact_fallback_is_removed():
    authored = 'ㅇ 현장 운영실적 7명에 근거하여 사업 성과의 후속 검증을 제언함.'
    xml = (paragraph(record(MARKER + '; 내부 메모')) + paragraph('3. 종합 평가 및 시사점')
           + paragraph(FALLBACK) + paragraph(authored))
    projected, _ = improve_achievement_readability(xml)
    assert FALLBACK not in projected
    assert '3. 종합 평가 및 시사점' in projected and authored in projected


def test_fallback_like_text_without_system_record_is_not_omitted():
    xml = paragraph('3. 종합 평가 및 시사점') + paragraph(FALLBACK)
    assert improve_achievement_readability(xml) == (xml, 0)


def test_semantic_narrative_probes_use_same_narrow_fallback_omission():
    from kodame_intake.report_exporter import _narrative_body_probes, _body_probes
    authored = 'ㅇ 확인된 교육 실적 7명과 검증된 후속 운영 기록에 따라 사업의 성과를 판단함.'
    raw = '\n'.join([record(MARKER), '3. 종합 평가 및 시사점', FALLBACK, authored])
    assert _narrative_body_probes('achievement', raw) == _body_probes('3. 종합 평가 및 시사점\n' + authored)
    changed = FALLBACK + ' 이 사업의 추가 해설을 보존함.'
    assert _narrative_body_probes('achievement', '\n'.join([record(MARKER), changed])) == _body_probes(changed)
    assert _narrative_body_probes('achievement', FALLBACK) == _body_probes(FALLBACK)
    internal_only = '\n'.join(['2. 성과지표별 목표 대비 실적 분석', record(MARKER), '3. 종합 평가 및 시사점', FALLBACK])
    assert _narrative_body_probes('achievement', internal_only) == []
    mixed = '\n'.join(['2. 성과지표별 목표 대비 실적 분석', record(MARKER), record('직접 작성한 해설')])
    assert _narrative_body_probes('achievement', mixed) == _body_probes('2. 성과지표별 목표 대비 실적 분석')


def test_section_preview_adapter_preserves_prepared_source_and_projects_only_during_patch(monkeypatch):
    from kodame_intake import theory_visual
    monkeypatch.setattr(theory_visual, 'current_llm_model', lambda: 'qa/mock')
    raw = {'achievement': record(MARKER + '; 근거 검토 이력') + '\n\n3. 종합 평가 및 시사점\n\nㅇ 종합 성과 해설을 보존함.'}
    source = deepcopy(raw)
    prepared, _ = prepare_hwpx_sections({}, raw, [], selected_parts={'achievement'})
    before = deepcopy(prepared)
    digest = theory_visual.theory_visual_input_digest({}, prepared, {})
    result = ADAPTER.patch_xml(template(), {}, prepared)
    result_xml, _ = improve_achievement_readability(result.xml)
    assert MARKER not in result_xml
    assert MARKER in prepared['achievement']
    assert raw == source and prepared == before
    assert theory_visual.theory_visual_input_digest({}, prepared, {}) == digest


def test_semantic_validator_requires_empty_system_note_and_still_checks_measurements(monkeypatch):
    from kodame_intake import report_exporter
    # Isolate the real achievement validator from unrelated chapter contracts.
    monkeypatch.setattr(report_exporter, 'NARRATIVE_VALIDATION_KEYS', {14: ('qa_body', 'achievement')})
    monkeypatch.setattr(report_exporter, 'review_values_for_section', lambda *args: {})
    monkeypatch.setattr(report_exporter, 'PDM_TABLE_PAGE_ROW_GROUPS', ())
    raw = '\n'.join(['2. 성과지표별 목표 대비 실적 분석', record(MARKER + '; 내부 설명'), '3. 종합 평가 및 시사점', FALLBACK])
    patched = patch_hwpx_achievement_table_xml(template(), {'achievement': raw})
    table = find_hwpx_table_span_by_text(patched, ['성과지표', '기초선', '달성도'], 20)[2]

    def validate(xml):
        data = BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('Contents/section5.xml', xml)
        return report_exporter._validate_semantic_coverage(data.getvalue(), {}, {'achievement': raw})

    assert validate(table)['achievement_rows'] == 1
    contaminated, _ = set_hwpx_table_cell_text_xml(table, 20 + ACHIEVEMENT_CELL_OFFSETS['note'], MARKER)
    with pytest.raises(RuntimeError, match='내부 분석 메모가 비고에 남음'):
        validate(contaminated)
    wrong_actual, _ = set_hwpx_table_cell_text_xml(table, 20 + ACHIEVEMENT_CELL_OFFSETS['endline'], '99명')
    with pytest.raises(RuntimeError, match='endline 셀 매핑 오류'):
        validate(wrong_actual)
