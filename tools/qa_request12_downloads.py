"""Exercise authorized user01 downloads; no account/password changes."""
import json, hashlib
from pathlib import Path
from uuid import UUID
import httpx
from fastapi import Request
from kodame_intake.auth import create_session,revoke_session
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME

PROJECT=UUID('05460961-f12e-4fe7-ba6f-3e36e27bd23d')
OUT=Path('/app/data/qa/request12-20260919/downloads');OUT.mkdir(parents=True,exist_ok=True)
pool.open();token=None;result={}
try:
    with tenant_context(system=True),connection() as c:
        row=c.execute("SELECT a.id FROM accounts a JOIN project_members m ON m.account_id=a.id WHERE a.email='user01@kodame.local' AND m.project_id=%s",(PROJECT,)).fetchone()
    token,_=create_session(row['id'],Request({'type':'http','headers':[(b'user-agent',b'ODAME request12 download QA')],'client':('127.0.0.1',0)}))
    with connection() as c,c.transaction():
        c.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '10 minutes' WHERE token_hash=%s",(PROJECT,hash_session_token(token)))
    with httpx.Client(base_url='http://kodame-redesign-web',cookies={SESSION_COOKIE_NAME:token},timeout=180,
        headers={'X-ODAME-Account':str(row['id']),'X-ODAME-Project':str(PROJECT)}) as client:
        for kind in ['grade-xlsx','grade-hwpx','lessons-pptx','lessons-hwpx','feedback-xlsx','feedback-pptx']:
            r=client.get('/api/v2/report/submissions/'+kind)
            result[kind]={'status':r.status_code}
            if r.status_code==200:
                name=kind+'.'+kind.split('-')[-1];(OUT/name).write_bytes(r.content)
                result[kind].update(size=len(r.content),sha256=hashlib.sha256(r.content).hexdigest())
            else:result[kind]['error']=r.text[:900]
            print(json.dumps({kind:result[kind]},ensure_ascii=False),flush=True)
        for kind in ['user-manual','evaluation-guide-v22','evaluation-report-hwp','evaluation-grade-xlsx','evaluation-grade-hwp','evaluation-lessons-pptx','evaluation-feedback-xlsm']:
            r=client.get('/api/v2/samples/templates/'+kind+'/download')
            result['template-'+kind]={'status':r.status_code,'size':len(r.content)}
        for kind in ['exports','presentations']:
            r=client.get('/api/v2/report/'+kind+'/latest');latest=r.json()
            if latest.get('download_url'):
                r=client.get(latest['download_url']);assert r.status_code==200
                (OUT/('report.'+('hwpx' if kind=='exports' else 'pptx'))).write_bytes(r.content)
        (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['status']==200 for r in result.values()),'Some download checks failed; see results.json'
finally:
    if token:revoke_session(token)
    pool.close()
