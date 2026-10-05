"""Readable printing without changing the official scoring matrix topology."""
from copy import deepcopy
from math import ceil
from lxml import etree as E

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
Q=lambda name:'{'+NS+'}'+name


def text_value(source,cell):
    if cell is None:return ''
    if cell.get('t')=='s':
        strings=E.fromstring(source.read('xl/sharedStrings.xml'))
        return ''.join(strings[int(cell.findtext(Q('v')))].itertext())
    return ''.join(cell.find(Q('is')).itertext()) if cell.find(Q('is')) is not None else cell.findtext(Q('v')) or ''


def row_height(sheet,number,height):
    data=sheet.find(Q('sheetData'));row=data.find(f"{Q('row')}[@r='{number}']")
    if row is None:row=E.SubElement(data,Q('row'),r=str(number))
    row.set('ht',str(height));row.set('customHeight','1')


def print_layout(sheet,*,paper='8',landscape=True):
    props=sheet.find(Q('sheetPr'))
    if props is None:props=E.Element(Q('sheetPr'));sheet.insert(0,props)
    fit=props.find(Q('pageSetUpPr'))
    if fit is None:fit=E.SubElement(props,Q('pageSetUpPr'))
    fit.set('fitToPage','1')
    setup=sheet.find(Q('pageSetup'))
    if setup is None:setup=E.SubElement(sheet,Q('pageSetup'))
    setup.attrib.pop('scale',None)
    setup.set('orientation','landscape' if landscape else 'portrait');setup.set('paperSize',paper)
    setup.set('fitToWidth','1');setup.set('fitToHeight','0')


def wrapped_style(styles,original,*,size=None,black=False):
    xfs=styles.find(Q('cellXfs'));style=deepcopy(xfs[int(original or 0)])
    alignment=style.find(Q('alignment'))
    if alignment is None:alignment=E.SubElement(style,Q('alignment'))
    alignment.set('wrapText','1');alignment.set('vertical','center');alignment.set('shrinkToFit','0')
    style.set('applyAlignment','1')
    if size or black:
        fonts=styles.find(Q('fonts'));font=deepcopy(fonts[int(style.get('fontId','0'))])
        if size:font.find(Q('sz')).set('val',str(size))
        if black:
            color=font.find(Q('color'))
            if color is None:color=E.SubElement(font,Q('color'))
            color.attrib.clear();color.set('rgb','FF202B3B')
        style.set('fontId',str(len(fonts)));fonts.append(font);fonts.set('count',str(len(fonts)))
    index=len(xfs);xfs.append(style);xfs.set('count',str(len(xfs)));return str(index)


def grade_layout(source,sheets,styles):
    formats=styles.find(Q('numFmts'))
    if formats is None:formats=E.Element(Q('numFmts'),count='0');styles.insert(0,formats)
    fmt=max([163]+[int(n.get('numFmtId')) for n in formats])+1
    E.SubElement(formats,Q('numFmt'),numFmtId=str(fmt),formatCode='0.0"점"');formats.set('count',str(len(formats)))
    score_styles={}
    for sheet in sheets:
        print_layout(sheet)
        for number in (4,5):
            row_height(sheet,number,48 if number==4 else 26)
            for cell in sheet.findall(f"{Q('sheetData')}/{Q('row')}[@r='{number}']/{Q('c')}"):
                cell.set('s',wrapped_style(styles,cell.get('s')))
        row_height(sheet,8,42)
        for number in range(9,58 if sheet is sheets[0] else 63):
            cell=sheet.find(f"{Q('sheetData')}/{Q('row')}[@r='{number}']/{Q('c')}[@r='G{number}']")
            text=text_value(source,cell)
            units=sum(1 if ord(c)>127 else .55 for c in text)
            height=max(25,ceil(units/45)*18+10)
            row_height(sheet,number,height)
        # Break at criterion boundaries, so merged questions never straddle
        # two printed pages. The official columns and cell values remain.
        breaks=sheet.find(Q('rowBreaks'))
        if breaks is not None:sheet.remove(breaks)
        points=[17,26,39,48]+([] if sheet is sheets[0] else [57])
        breaks=E.SubElement(sheet,Q('rowBreaks'),count=str(len(points)),manualBreakCount=str(len(points)))
        for point in points:E.SubElement(breaks,Q('brk'),id=str(point),min='0',max='16383',man='1')
        for cell in sheet.findall(f"{Q('sheetData')}/{Q('row')}/{Q('c')}"):
            if cell.get('r','').startswith('D') and cell.get('t') not in ('inlineStr','s','str') and cell.find(Q('v')) is not None:
                original=cell.get('s','0')
                if original not in score_styles:
                    xfs=styles.find(Q('cellXfs'));style=deepcopy(xfs[int(original)]);style.set('numFmtId',str(fmt));style.set('applyNumberFormat','1')
                    score_styles[original]=str(len(xfs));xfs.append(style);xfs.set('count',str(len(xfs)))
                cell.set('s',score_styles[original])


def evidence_sheet(source,styles,records,title,value):
    sheet=E.Element(Q('worksheet'),nsmap={None:NS});cols=E.SubElement(sheet,Q('cols'))
    for i,width in enumerate((27,9,85),1):E.SubElement(cols,Q('col'),min=str(i),max=str(i),width=str(width),customWidth='1')
    E.SubElement(sheet,Q('sheetData'))
    body=wrapped_style(styles,48,size=11,black=True)
    value(sheet,'A1','종료평가 판정 근거 · 저장된 평가 결과')
    value(sheet,'A2',title);value(sheet,'A3','평가 질문');value(sheet,'B3','점수');value(sheet,'C3','판정 근거 및 한계')
    for row,record in enumerate(records,4):
        for col,item in zip('ABC',record):value(sheet,f'{col}{row}',item)
        units=sum(1 if ord(c)>127 else .55 for c in str(record[2]))
        row_height(sheet,row,max(88,ceil(units/48)*16+20))
    for c in sheet.findall(f"{Q('sheetData')}/{Q('row')}/{Q('c')}"):c.set('s',body)
    row_height(sheet,1,30);row_height(sheet,2,48);row_height(sheet,3,30)
    merges=E.SubElement(sheet,Q('mergeCells'),count='2')
    for ref in ('A1:C1','A2:C2'):E.SubElement(merges,Q('mergeCell'),ref=ref)
    print_layout(sheet,paper='9',landscape=False)
    workbook=E.fromstring(source.read('xl/workbook.xml'));rels=E.fromstring(source.read('xl/_rels/workbook.xml.rels'))
    sheets=workbook.find(Q('sheets'));index=len(sheets);rid='rIdEvidence'
    E.SubElement(sheets,Q('sheet'),name='판정 근거',sheetId=str(index+1),attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':rid})
    E.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id=rid,Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',Target='worksheets/sheet3.xml')
    types=E.fromstring(source.read('[Content_Types].xml'))
    E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',PartName='/xl/worksheets/sheet3.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
    names=workbook.find(Q('definedNames'))
    if names is None:names=E.SubElement(workbook,Q('definedNames'))
    E.SubElement(names,Q('definedName'),name='_xlnm.Print_Area',localSheetId=str(index)).text=f"'판정 근거'!$A$1:$C${3+len(records)}"
    E.SubElement(names,Q('definedName'),name='_xlnm.Print_Titles',localSheetId=str(index)).text="'판정 근거'!$3:$3"
    return {k:E.tostring(v) for k,v in {'xl/worksheets/sheet3.xml':sheet,'xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':rels,'[Content_Types].xml':types}.items()}
