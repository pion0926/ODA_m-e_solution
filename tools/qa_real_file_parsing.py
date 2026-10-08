"""Read only user-supplied files locally. No AI, network calls or DB writes."""
import json,time,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from kodame_intake.parse_sandbox import parse_isolated
from kodame_intake.source_locations import locate
assert os.getenv('KODAME_QA')=='1'
root=Path('/source'); started=time.monotonic()
files=sorted(p for p in root.rglob('*') if p.suffix.lower() in {'.pdf','.hwp','.hwpx','.xlsx','.docx','.pptx'})
def run(path):
    start=time.monotonic()
    try:
        text,method=parse_isolated(path,path.suffix.lower())
        status={'status':'passed','characters':len(text),'method':method,
                'tail_location':locate(text,text[-min(100,len(text)):],start=max(0,len(text)-100))}
    except Exception as exc:
        status={'status':'bounded_error','error':str(exc),'type':type(exc).__name__}
    return {'file':str(path.relative_to(root)),**status,'seconds':round(time.monotonic()-start,2)}
with ThreadPoolExecutor(max_workers=4) as executor:
    results=list(executor.map(run,files))
report={'files':len(results),'passed':sum(r['status']=='passed' for r in results),
        'bounded_errors':sum(r['status']!='passed' for r in results),'seconds':round(time.monotonic()-started,2),
        'scope':'local parsing only; no document text saved or sent externally','results':results}
Path('/qa/real-file-parsing.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
