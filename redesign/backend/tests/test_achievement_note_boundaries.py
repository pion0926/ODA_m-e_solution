"""Explicit record fields preserve supplementary targets as notes, not current values."""
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

import pytest

from backend.oda_me.hwpx.patchers import (
    achievement_item_fields, find_hwpx_tag_spans, get_hwpx_xml_scope_text,
    parse_achievement_items, patch_hwpx_achievement_table_xml,
)
from kodame_intake.hwpx_layout.achievement_readability import improve_achievement_readability
from kodame_intake.hwpx_layout.tables import style_achievement_table_xml
from kodame_intake.hwpx_layout.overflow import resolve_detail_text


def record(ident, target, actual, note):
    return (f'- [{ident}]: 성과지표: 합성 지표 {ident} / 기초선: 미기재 / 목표치: {target}'
            f' / 종료선 또는 현재 실적: {actual} / 대비 결과: 기간 확인 필요'
            f' / 지표입증수단(MOV): 확인서 / 비고: {note}')


@pytest.mark.parametrize('target,actual,alternatives', [
    ('확인 필요', '실적 미확인', '2027년 72%, 2028년 91% 이상'),
    ('12명', '7명', '전국 30명, 한 지역 12명'),
    ('4회', '2회', '2027년 4회, 누적 9회'),
    ('2.5억원', '1.2억원', '이전 3.6억원, 환율 적용 전 20만 달러'),
])
def test_note_labels_never_replace_actual_fields_or_drop_alternative_values(target, actual, alternatives):
    note = ('저장된 결과; 목표: 기간과 범위를 대조함; 실적: 같은 모집단만 비교함; '
            f'다른 자료의 목표 {alternatives}: 기간·범위 차이 확인 필요')
    raw = record('outcome-4-1', target, actual, note)
    fields = achievement_item_fields(parse_achievement_items(raw)[0], 0)
    assert fields['target'] == target
    assert fields['endline'] == actual
    assert fields['note'] == note
    assert fields['mov'] == '확인서'
    paragraph = f'<hp:p id="1" paraPrIDRef="92" pageBreak="0"><hp:run><hp:t>{raw}</hp:t></hp:run></hp:p>'
    projected, count = improve_achievement_readability(paragraph)
    assert count == 1 and note in get_hwpx_xml_scope_text(projected)
    assert raw.endswith(note)  # Reader projection does not mutate the saved draft.


def test_multiple_long_notes_flow_through_actual_table_without_losing_dates_or_units():
    notes = [
        ('선택 근거; 목표: 연도별 범위를 유지함; ' +
         (f'자료 {index}: 2027년 {index + 12}명, 2028년 {index + 31}명이며 지역 범위를 확인함. ' * 140) +
         f'; 다른 자료의 목표 2030년 {index + 45}명: 비교 전 기간 확인 필요')
        for index in range(2)
    ]
    raw = '\n'.join(record(f'outputs-{i + 1}-1', '12명', '7명', note) for i, note in enumerate(notes))
    fields = [achievement_item_fields(item, i) for i, item in enumerate(parse_achievement_items(raw))]
    assert [f['note'] for f in fields] == notes
    assert all(f['target'] == '12명' and f['endline'] == '7명' for f in fields)
    template = Path(__file__).resolve().parents[3] / 'samples' / '5-1. 종료평가 결과보고서 placeholder.hwpx'
    with zipfile.ZipFile(template) as archive:
        xml = archive.read('Contents/section5.xml').decode('utf-8')
    patched = patch_hwpx_achievement_table_xml(xml, {'achievement': raw})
    styled, _ = style_achievement_table_xml(patched)
    ET.fromstring(styled)
    visible = re.sub(r'\s+', '', get_hwpx_xml_scope_text(styled))
    references = set(re.findall(r'\[S\d+ 상세\]', get_hwpx_xml_scope_text(styled)))
    restored = [re.sub(r'\s+', '', resolve_detail_text(styled, ref)) for ref in references]
    for note in notes:
        expected = re.sub(r'\s+', '', note)
        assert expected in visible or expected in restored
    for start, end in find_hwpx_tag_spans(styled, 'hp:tbl'):
        table = styled[start:end]
        if '성과지표' not in get_hwpx_xml_scope_text(table):
            continue
        assert int(re.search(r'<hp:sz\b[^>]*height="(\d+)"', table)[1]) <= 44000
    assert '(계속)' in styled  # Long preserved notes get actual continuation output.


def test_legacy_semicolon_fields_keep_existing_boundaries():
    item = '성과지표: 교육 이수; 목표치: 12명; 종료선: 7명; 비고: 후속 확인'
    fields = achievement_item_fields(item, 0)
    assert fields['target'] == '12명' and fields['endline'] == '7명'
    assert fields['note'] == '후속 확인'


def test_slashes_and_field_words_inside_explicit_notes_remain_literal():
    note = '비교 기준; 목표: 2027/2028년; 실적: 단위 확인; 근거 위치: 본문 3쪽; 판단: 동일 기간만 비교'
    item = parse_achievement_items(record('1.2-3', '12건', '6건', note))[0]
    assert achievement_item_fields(item, 0)['note'] == note


def test_final_note_slash_labels_cannot_override_table_fields_or_absorb_narrative():
    note = '현재 목표는 같은 범위로 비교함 / 목표치: 2028년 91% / 실적: 다른 지역 73%'
    second = record('outputs-2-1', '15명', '9명', '다음 지표는 별개 기록임')
    raw = record('outcome-1-1', '82%', '68%', note) + '\n다음 일반 문장은 비고가 아님\n' + second + '\n별도 종합 설명도 비고가 아님'
    items = parse_achievement_items(raw)
    assert len(items) == 2
    first, other = [achievement_item_fields(item, i) for i, item in enumerate(items)]
    assert first['target'] == '82%' and first['endline'] == '68%'
    assert first['note'] == note
    assert other['target'] == '15명' and other['endline'] == '9명'
    assert other['note'] == '다음 지표는 별개 기록임'


def test_canonical_multiline_note_is_preserved_after_its_explicit_field_boundary():
    note = ('원래 선택 이유; 목표: 기간 비교 필요'
            '\n목표치: 2030년 97% 이상; 기간과 범위 확인 필요'
            '\n실적: 비교 문서의 75%는 현재 실적이 아님')
    # The canonical field representation has already separated the final note.
    # Raw authoring records remain one line and never absorb following prose.
    item = '지표 ID: outcome-1-1\n성과지표: 합성 지표\n목표치: 82%\n종료선: 68%\n비고: ' + note
    fields = achievement_item_fields(item, 0)
    assert fields['target'] == '82%' and fields['endline'] == '68%'
    assert fields['note'] == note


@pytest.mark.parametrize('canonical,alias', [
    ('성과지표', '성과 지표 명칭'),
    ('목표치', '목표치 (Targets)'),
    ('실적', '실적 (현재시점)'),
    ('실적', '실적 (누적/최신)'),
    ('검증수단', '검증수단 (MOV)'),
])
def test_normalized_id_rows_with_any_legacy_alias_keep_the_existing_parser(canonical, alias):
    item = ('지표 ID: outputs-3-1\n성과지표: 교육 이수 인원\n기초선: 0명'
            '\n목표치: 12명\n실적: 7명\n검증수단: 출석부\n비고: 기간을 확인함')
    item = item.replace('\n' + canonical + ':', '\n' + alias + ':', 1)
    fields = achievement_item_fields(item, 0)
    assert fields['indicator'] == '교육 이수 인원'
    assert fields['target'] == '12명' and fields['endline'] == '7명'
    assert fields['mov'] == '출석부' and fields['note'] == '기간을 확인함'


def test_alias_labels_inside_canonical_final_note_do_not_trigger_legacy_fallback():
    note = ('원래 선택 이유; 목표: 현재 범위를 유지함\n실적 (현재시점): 다른 지역 9명'
            '\n목표치 (Targets): 다음 연도 20명 / 검증수단 (MOV): 추후 보고서')
    item = ('지표 ID: outputs-3-1\n성과지표: 교육 이수 인원\n목표치: 12명'
            '\n종료선: 7명\n지표입증수단(MOV): 출석부\n비고: ' + note)
    fields = achievement_item_fields(item, 0)
    assert fields['target'] == '12명' and fields['endline'] == '7명'
    assert fields['mov'] == '출석부' and fields['note'] == note


def test_supported_long_endline_label_in_normalized_id_record_keeps_actual_value():
    item = ('지표 ID: outputs-3-1\n성과지표: 교육 이수 인원\n목표치: 12명'
            '\n종료선 또는 현재 실적: 7명\n지표입증수단(MOV): 출석부'
            '\n비고: 다음 연도 목표는 별도임; 목표: 20명')
    fields = achievement_item_fields(item, 0)
    assert fields['target'] == '12명' and fields['endline'] == '7명'
    assert fields['mov'] == '출석부'
    assert fields['note'] == '다음 연도 목표는 별도임; 목표: 20명'
