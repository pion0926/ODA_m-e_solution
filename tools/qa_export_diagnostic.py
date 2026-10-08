import json,zipfile
from pathlib import Path
from kodame_intake.hwpx_layout.spacing import _top_level_paragraphs,_visible_text
paths=list(Path('/app/data').glob('**/diagnostics/a04f0fd5-792d-4859-b37f-319afbed5f07/candidate.hwpx'))
with zipfile.ZipFile(paths[0]) as archive:
    xml=archive.read('Contents/section5.xml').decode()
    paragraphs=_top_level_paragraphs(xml)
    print(json.dumps([_visible_text(p)[:200] for a,b,p in paragraphs],ensure_ascii=False))
    for n,(a,b,p) in enumerate(paragraphs):
        if '종합 평가' in _visible_text(p):
            print(json.dumps({'previous':paragraphs[max(0,n-1)][2][:1200],'heading':p[:1600]},ensure_ascii=False))
