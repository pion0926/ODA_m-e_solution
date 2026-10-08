"""Inspect supplied templates without modifying originals or running macros."""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from openpyxl import load_workbook

root=Path(__file__).resolve().parents[1]
output=[]
book=load_workbook(root/'samples/5-2. 종료평가 등급 결과표(엑셀버전).xlsx',data_only=False)
for sheet in book:
    rows=[]
    for row in sheet:
        cells=[f'{c.coordinate}: {c.value}' for c in row if c.value is not None]
        if cells: rows.append(cells)
    output.append({'sheet':sheet.title,'rows':rows,'merged':[str(r) for r in sheet.merged_cells.ranges]})
    print(json.dumps({'sheet':sheet.title,'cells':[[c.coordinate,str(c.value)] for row in sheet for c in row if c.value is not None and (c.data_type=='f' or c.column in (2,3,4))]},ensure_ascii=False))
with ZipFile(root/'samples/5-3. 분야별 평가 교훈 리포트 양식.pptx') as z:
    slides=sorted((n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')),key=lambda n:int(n.split('slide')[-1].split('.')[0]))
    for name in slides:
        xml=ET.fromstring(z.read(name)); texts=[e.text for e in xml.iter() if e.tag.endswith('}t') and e.text]
        output.append({'slide':name,'texts':texts})
        print(json.dumps({'slide':name,'text_count':len(texts),'first':texts[:36]},ensure_ascii=False))
out=root/'tmp/request12-20260919';out.mkdir(parents=True,exist_ok=True)
(out/'template-inventory.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
