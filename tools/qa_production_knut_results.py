"""Check saved production results and actual exported files without AI or writes to DB."""
import hashlib,json,re,zipfile
from pathlib import Path
from lxml import etree as ET
from kodame_intake.report_grade_scores import QUESTION_SLOTS
from kodame_intake.submission_exports import QUESTION_ROWS

root=Path('/app/data/qa/production-knut-20260920')
read=lambda name:json.loads((root/(name+'.json')).read_text(encoding='utf-8'))
evaluation=read('evaluations'); sections={s['part_id']:s for s in read('sections')['items']}
assert evaluation['status']=='completed' and evaluation['document_count']==73
assert len(sections)==27 and all(s['status']=='draft' and s['content'].strip() for s in sections.values())
assert evaluation['lifecycle']['evaluation_current'] and evaluation['lifecycle']['report_current']
slots=json.loads(sections['grade']['content'])['slots']
criteria={c['id']:c for c in evaluation['criteria']}
checked=[]
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(root/'knut-grade-xlsx.xlsx') as archive:
    sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
def cell(address):
    node=sheet.find(f".//s:c[@r='{address}']",NS);assert node is not None,address
    return ''.join(node.itertext()) if node.get('t')=='inlineStr' else node.findtext('s:v',namespaces=NS)
for criterion_id,suffixes in QUESTION_SLOTS.items():
    criterion=criteria[criterion_id]
    questions={q['question_id']:q for q in criterion['question_assessments']}
    for index,suffix in enumerate(suffixes,1):
        qid=f'{criterion_id}-q{index}';score=questions[qid]['score']
        wanted='판정보류' if score is None else f'{float(score):g}점'
        assert slots[f'{criterion_id}_{suffix}_score']==wanted,(qid,wanted)
        value=cell(f'D{QUESTION_ROWS[criterion_id][0][index-1]}')
        assert value=='판정보류' if score is None else float(value)==float(score)
        checked.append({'question':qid,'score':score,'report_matches':True,'excel_matches':True})
assert evaluation['overall']['score'] is None and slots['overall_score']=='판정보류'
assert cell('D58')=='판정보류'
report=root/'knut-report.hwpx'
with zipfile.ZipFile(report) as archive:
    assert archive.testzip() is None
    xml_text='\n'.join(' '.join(ET.fromstring(archive.read(name)).xpath('//*[local-name()="t"]/text()'))
                       for name in sorted(archive.namelist()) if re.match(r'Contents/section\d+\.xml$',name))
    assert '판정보류' in xml_text
    assert '판정보류점' not in xml_text and '판정보류/20점' not in xml_text
    assert '2029' in xml_text and '2022' in xml_text
    assert 'section9_eval_purpose_slots_v1' not in xml_text
    assert 'evaluation_purpose_scope_body' not in xml_text
    assert not re.search(r'"schema"\s*:\s*"section\d+[ _]',xml_text)
    assert not re.search(r'\{\{CURRENT_|<hp:|01 사업기본자료 사업기본자료',xml_text)
    (root/'hwpx-visible-text.txt').write_text(xml_text,encoding='utf-8')
result={'documents':73,'report_sections':27,'question_score_checks':checked,'overall':'판정보류',
        'hwpx_bytes':report.stat().st_size,'hwpx_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
        'period_consistent':True,'raw_json_not_visible':True}
(root/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
