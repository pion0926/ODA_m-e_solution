"""Separate, editable submissions populated from the saved evaluation/report.

Office XML patching keeps the supplied workbook layout and validation intact.
No macros or formula-like user text are executed; missing facts stay explicit.
"""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import math
import re

from lxml import etree as ET
from .dac_rules import mean_score, rounded
from .evaluation_criteria import grade
from .submission_spreadsheet_layout import grade_layout, evidence_sheet, print_layout, wrapped_style

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'samples').is_dir())
TEMPLATES = ROOT / 'samples/koica-v2.2-20260919'
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
Q = lambda name: '{'+NS+'}'+name
QUESTION_ROWS = {
    'relevance': ([9, 13], 17), 'coherence': ([18, 22], 26),
    'effectiveness': ([27, 31, 35], 39), 'efficiency': ([40, 44], 48),
    'sustainability': ([49, 53], 57),
}


def _cell(sheet, address):
    data = sheet.find(Q('sheetData'))
    row_number = int(re.search(r'\d+', address)[0])
    row = data.find(f"{Q('row')}[@r='{row_number}']")
    if row is None:
        row = ET.SubElement(data, Q('row'), r=str(row_number))
    cell = row.find(f"{Q('c')}[@r='{address}']")
    if cell is None:
        cell = ET.SubElement(row, Q('c'), r=address)
    return cell


def _value(sheet, address, value, *, formula=None):
    cell = _cell(sheet, address)
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop('t', None)
    if formula:
        ET.SubElement(cell, Q('f')).text = formula
        if isinstance(value, str):
            cell.set('t', 'str')
        ET.SubElement(cell, Q('v')).text = str(value)
    elif isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError('유효하지 않은 점수입니다.')
        ET.SubElement(cell, Q('v')).text = str(value)
    else:
        cell.set('t', 'inlineStr')
        text = ET.SubElement(ET.SubElement(cell, Q('is')), Q('t'))
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = str(value or '')


def _package(template, edits, *, strip_macros=False):
    out = BytesIO()
    with ZipFile(template) as source, ZipFile(out, 'w', ZIP_DEFLATED) as target:
        for item in source.infolist():
            name = item.filename
            if 'calcChain' in name or (strip_macros and ('vbaProject' in name or 'vbaData' in name)):
                continue
            data = edits.get(name, source.read(name))
            if name == '[Content_Types].xml' or name.endswith('.rels'):
                xml = ET.fromstring(data)
                for node in list(xml):
                    values = ' '.join(node.attrib.values())
                    if 'calcChain' in values or (strip_macros and ('vbaProject' in values or 'vbaData' in values)):
                        xml.remove(node)
                    if strip_macros and node.get('ContentType') == 'application/vnd.ms-excel.sheet.macroEnabled.main+xml':
                        node.set('ContentType', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
                data = ET.tostring(xml, encoding='UTF-8', xml_declaration=True)
            target.writestr(item, data)
        for name,data in edits.items():
            if name not in source.namelist():target.writestr(name,data)
    return out.getvalue()


def grade_workbook(title, criteria):
    template = TEMPLATES / '5-2. 종료평가 등급 결과표(엑셀버전).xlsx'
    with ZipFile(template) as source:
        sheet = ET.fromstring(source.read('xl/worksheets/sheet1.xml'))
        after = ET.fromstring(source.read('xl/worksheets/sheet2.xml'))
        styles = ET.fromstring(source.read('xl/styles.xml'))
    _value(sheet, 'C4', title)
    _value(sheet, 'C5', '확인 필요')
    scores, records = [], []
    for criterion_id, (rows, mean_row) in QUESTION_ROWS.items():
        criterion = next((c for c in criteria if c['id'] == criterion_id), {})
        questions = {q['question_id']: q for q in criterion.get('question_assessments', [])}
        values = []
        for n, row in enumerate(rows, 1):
            q = questions.get(f'{criterion_id}-q{n}', {})
            score = q.get('score')
            if score is not None and not 1 <= float(score) <= 4:
                raise ValueError('질문 점수는 1~4점 범위여야 합니다.')
            values.append(score)
            _value(sheet, f'D{row}', score if score is not None else '판정보류')
            # E is the official /4-point denominator. Keep it intact and
            # provide complete rationale in a readable companion worksheet.
            rationale = str(q.get('finding') or '판정 근거 확인 필요')
            limitations = q.get('limitations') or []
            if limitations:
                rationale += '\n한계: '+('; '.join(map(str, limitations)) if isinstance(limitations, list) else str(limitations))
            records.append([f'{criterion_id}-q{n}',score if score is not None else '판정보류',rationale])
        average = mean_score(values)
        if average != criterion.get('score'):
            raise ValueError(f'{criterion_id}: 저장된 질문 점수와 기준 평균이 일치하지 않습니다. 재평가가 필요합니다.')
        scores.append(average)
        refs = ','.join(f'D{row}' for row in rows)
        _value(sheet, f'D{mean_row}', average if average is not None else '판정보류',
               formula=f'IF(COUNT({refs})={len(rows)},ROUND(AVERAGE({refs}),1),"판정보류")')
    total = rounded(sum(scores)) if all(s is not None for s in scores) else None
    _value(sheet, 'D58', total if total is not None else '판정보류',
           formula='IF(COUNT(D17,D26,D39,D48,D57)=5,ROUND(SUM(D17,D26,D39,D48,D57),1),"판정보류")')
    rating = grade(total)[1] if total is not None else '판정보류'
    _value(sheet, 'D59', rating, formula='IF(ISNUMBER(D58),IF(D58>=18,"매우 성공적",IF(D58>=14,"성공적",IF(D58>=10,"부분 성공적","미흡"))),"판정보류")')
    # Post-evaluation remains an unfilled reference sheet: no sixth score invented.
    _value(after, 'C4', '사후평가용 참고 양식 · 본 파일은 종료평가 결과만 산출')
    _value(after, 'D62', '미입력', formula='IF(COUNT(D58)=1,D58,"미입력")')
    _value(after, 'D63', '미입력', formula='IF(COUNT(D17,D26,D39,D48,D57,D62)=6,SUM(D17,D26,D39,D48,D57,D62),"미입력")')
    _value(after, 'D64', '미입력', formula='IF(COUNT(D17,D26,D39,D48,D57,D62)=6,IF(D63>=18,"매우 성공적",IF(D63>=14,"성공적",IF(D63>=10,"부분 성공적","미흡"))),"미입력")')
    with ZipFile(template) as source:
        grade_layout(source,[sheet,after],styles)
        edits=evidence_sheet(source,styles,records,title,_value)
    edits.update({'xl/worksheets/sheet1.xml': ET.tostring(sheet), 'xl/worksheets/sheet2.xml': ET.tostring(after),'xl/styles.xml':ET.tostring(styles)})
    return _package(template, edits)


def feedback_records(title, content):
    from backend.oda_me.hwpx.patchers import parse_feedback_items
    parsed = parse_feedback_items(content)
    if not parsed:
        raise ValueError('저장된 환류과제에서 제출할 항목을 찾지 못했습니다. 환류과제를 먼저 작성해 주세요.')
    records = []
    for i, item in enumerate(parsed, 1):
        records.append([i, title, '환류과제 절 · 최종 쪽수 확인 필요', item['task'],
            item['reason'], item['owner']+' (제안·합의 확인 필요)',
            item.get('due_date') or '확인 필요', '유관부서 검토 필요',
            '기대효과·미이행 영향 검토 필요', '위험요인·대응방안 검토 필요',
            '면담 실시 여부 확인 필요', item.get('opinion') or '의견 반영 여부 확인 필요'])
    return records


FEEDBACK_HEADERS = ['No.', '평가사업명', '페이지', '환류과제명', '환류과제 개요', '이행주체(부서)',
    '이행시기', '현행방식과의 차별성 및 상충관계', '기대효과/미이행시 부정적 파급효과',
    '위험요인 및 대응방안', '유관부서 면담여부', '유관부서 주요 의견 반영사항']


def feedback_workbook(title, content):
    template = TEMPLATES / 'forms/5-4. 평가 환류과제 이행방안 양식.xlsm'
    with ZipFile(template) as source:
        sheet = ET.fromstring(source.read('xl/worksheets/sheet1.xml'))
        workbook = ET.fromstring(source.read('xl/workbook.xml'))
        styles = ET.fromstring(source.read('xl/styles.xml'))
    records = feedback_records(title, content)
    _value(sheet, 'A1', '평가 환류과제 이행방안 · 검토안')
    # Remove every sample value and unused numbered row in the original template.
    for row in sheet.find(Q('sheetData')):
        if int(row.get('r')) >= 4:
            for cell in list(row):
                _value(sheet, cell.get('r'), '')
    for row_n, record in enumerate(records, 4):
        for col_n, value in enumerate(record):
            _value(sheet, f'{chr(65+col_n)}{row_n}', value)
        row = sheet.find(f"{Q('sheetData')}/{Q('row')}[@r='{row_n}']")
        row.set('ht', str(min(380, max(150, max(len(str(v)) for v in record) * .72))))
        row.set('customHeight', '1')
    defined = workbook.find(Q('definedNames'))
    if defined is not None:
        for node in defined:
            if node.get('name') == '_xlnm.Print_Area':
                node.text = "'(평가팀 작성) 환류과제 이행방안'!$A$1:$L$"+str(3+len(records))
    setup = sheet.find(Q('pageSetup'))
    if setup is not None:
        setup.set('orientation', 'landscape'); setup.set('fitToWidth', '1'); setup.set('fitToHeight', '0')
    print_layout(sheet)
    style_map={}
    for row in sheet.find(Q('sheetData')):
        if int(row.get('r')) >=4:
            for cell in row:
                original=cell.get('s','0')
                if original not in style_map:style_map[original]=wrapped_style(styles,original,black=True)
                cell.set('s',style_map[original])
    return _package(template, {'xl/worksheets/sheet1.xml':ET.tostring(sheet), 'xl/workbook.xml':ET.tostring(workbook),'xl/styles.xml':ET.tostring(styles)}, strip_macros=True)
