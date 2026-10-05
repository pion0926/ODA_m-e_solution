"""Enumerate explicit spreadsheet target/actual rows without model selection."""
import hashlib
import re


def paired_rows(text):
    """Only unambiguous labelled columns; do not infer table semantics from positions."""
    sheet=''
    header=None
    result=[]
    for line_number,line in enumerate(text.splitlines(),1):
        if line.startswith('[시트:'):
            sheet=line
            header=None
            continue
        cells={m[0]:(m[1],m[2].strip()) for m in re.findall(r'(?:^| \| )([A-Z]+)(\d+)=(.*?)(?= \| [A-Z]+\d+=|$)',line)}
        labels={value[1].replace(' ',''):column for column,value in cells.items()}
        target=next((labels[x] for x in ('목표','목표값','목표치') if x in labels),None)
        actual=next((labels[x] for x in ('실적','실적값','실적치') if x in labels),None)
        metric=next((labels[x] for x in ('성과지표','지표','지표명') if x in labels),None)
        if target and actual and metric:
            header=(line,target,actual,metric)
            continue
        if not header or not all(c in cells for c in header[1:]):
            continue
        _,target,actual,metric=header
        values=[]
        for column in (target,actual):
            tokens=re.findall(r'-?\d[\d,]*(?:\.\d+)?',cells[column][1])
            if len(tokens)!=1:
                break
            values.append(float(tokens[0].replace(',','')))
        if len(values)!=2 or values[0]<=0 or values[1]<0:
            continue
        quote=header[0]+'\n...\n'+line
        if len(quote)>3500:
            continue
        status_column=next((column for column,value in re.findall(r'([A-Z]+)\d+=(.*?)(?= \| [A-Z]+\d+=|$)',header[0]) if value.strip() in {'비고','상태'}),None)
        status_text=cells.get(status_column,('',''))[1]
        metric_text=cells[metric][1]
        # Counts of delivered activities/assets do not establish beneficiary
        # change. Ambiguous indicators remain for evidence-based adjudication.
        output_count=bool(re.search(r'회의|교과목|결과보고서|교재|기자재|요구사항조사|공동연구.*횟수|학술대회|봉사활동.*횟수|교육.*횟수|강사.*양성|네트워크.*구축',metric_text))
        if '조사' in metric_text and cells[target][1].endswith('회') and cells[actual][1].endswith('회'):
            output_count=True
        result.append({'metric':cells[metric][1],'target':values[0],'actual':values[1],
            'target_text':cells[target][1],'actual_text':cells[actual][1],
            'status_text':status_text,
            'measurement_level':'activity_output' if output_count else 'requires_review',
            'quote':quote,'finding':'표의 명시적 목표·실적 열에서 추출한 행. 기간·대상·단위·목표시점은 별도 검토 필요.',
            'locator':{'section':sheet,'row':cells[metric][0],'start_line':line_number,'chunk_start':0,
                       'chunk_end':len(text),'text_sha256':hashlib.sha256(text.encode()).hexdigest()}})
    return result
