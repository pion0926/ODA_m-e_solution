"""Keep PDM mapping records in tables and show their interpretation as prose."""
import re
from backend.oda_me.hwpx.achievement_records import ACHIEVEMENT_RECORD_RE
from backend.oda_me.hwpx.performance_notes import (
    SYSTEM_INTERPRETATION_OMITTED, system_performance_interpretation_omissions,
)
from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans, get_hwpx_xml_scope_text, set_hwpx_xml_scope_text,
    parse_achievement_items, achievement_export_fields,
)

def improve_achievement_readability(xml: str) -> tuple[str, int]:
    tables = find_hwpx_tag_spans(xml, 'hp:tbl')
    edits, seen = [], set()
    omitted_records, retained_records = 0, 0
    narrative_paragraphs = []
    for start, end in find_hwpx_tag_spans(xml, 'hp:p'):
        if any(a < start < b for a,b in tables):
            continue
        paragraph = xml[start:end]
        if '<hp:tbl' in paragraph:
            continue
        text = get_hwpx_xml_scope_text(paragraph).strip()
        if text:
            narrative_paragraphs.append((start, end, text))
        match = ACHIEVEMENT_RECORD_RE.match(text)
        if match:
            records = parse_achievement_items(text)
            if len(records) != 1:
                raise ValueError('성과지표 해설 변환은 독립된 지표 레코드가 필요합니다.')
            fields = achievement_export_fields(records[0], 0)
            if fields.get('_system_note_omitted'):
                edits.append((start, end, ''))
                omitted_records += 1
                continue
            retained_records += 1
            note = fields['note'].strip()
            if not note:
                raise ValueError(f"성과지표 해설 누락: {match[1]}")
            label = match[1].lower()
            # Bare PDM IDs are valid, but do not imply a result level.
            group = ('성과(Outcome)' if label.startswith('outcome') else
                     '산출물(Output)' if label.startswith('output') else '지표')
            detail = set_hwpx_xml_scope_text(paragraph, '- ' + note.rstrip('.') + '.')
            prefix = ''
            if group not in seen:
                heading = set_hwpx_xml_scope_text(paragraph, 'ㅇ ' + group + '의 주요 진척과 확인 과제')
                heading = re.sub(r'paraPrIDRef="\d+"', 'paraPrIDRef="69"', heading, count=1)
                # The landscape table can consume the entire body area. Start
                # the first prose group on a fresh page so readers do not clip
                # the following generated paragraphs below the last table.
                if not seen:
                    heading = re.sub(r'pageBreak="[01]"', 'pageBreak="1"', heading, count=1)
                heading = re.sub(r'(<hp:p\b[^>]*\bid=")\d+', r'\g<1>2147483648', heading, count=1)
                prefix = heading
                seen.add(group)
            edits.append((start, end, prefix + detail))
        elif text == '2. 성과지표별 목표 대비 실적 분석':
            heading = set_hwpx_xml_scope_text(paragraph,'2. 성과 수준별 주요 진척과 한계')
            heading = re.sub(r'pageBreak="[01]"', 'pageBreak="1"', heading, count=1)
            edits.append((start,end,heading))
        elif text.startswith('최신 사업설계매트릭스(PDM)에 명시된 성과 및 산출물 지표를 기준으로 한 지표별 세부 실적'):
            edits.append((start,end,set_hwpx_xml_scope_text(paragraph,'성과 및 산출물 단계별 주요 진척과 추가 확인이 필요한 사항을 요약함.')))
        elif text in {'IV. 성과 달성도', 'IV. 성과달성도'} and '<hp:secPr' in paragraph:
            # A section already starts on a fresh page. Do not add another break.
            edits.append((start,end,re.sub(r'pageBreak="1"','pageBreak="0"',paragraph,count=1)))
    if omitted_records:
        # This exact generic fallback describes the system's comparison rule,
        # not a project conclusion. Preserve authored interpretations and any
        # additional narrative even when they mention similar concepts.
        omitted = system_performance_interpretation_omissions(
            [text for start, end, text in narrative_paragraphs], True, not retained_records)
        omitted_values = {
            narrative_paragraphs[index][0]: (
                SYSTEM_INTERPRETATION_OMITTED
                if narrative_paragraphs[index][2] == '3. 종합 평가 및 시사점' else ''
            ) for index in omitted
        }
        edited_starts = {start for start, end, value in edits}
        edits = [(start, end, omitted_values.get(start, value)) for start, end, value in edits]
        edits.extend((start, end, omitted_values[start]) for start, end, text in narrative_paragraphs
                     if start in omitted_values and start not in edited_starts)
    edits.sort(key=lambda item: item[0])
    for start,end,value in reversed(edits):
        xml = xml[:start] + value + xml[end:]
    return xml, len(edits)
