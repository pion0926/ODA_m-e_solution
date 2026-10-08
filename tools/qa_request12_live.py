"""Authorized user01 QA; short-lived session, no password/account changes."""
import argparse, hashlib, json, time
from pathlib import Path
from uuid import UUID
import httpx
from fastapi import Request
from kodame_intake.auth import create_session, revoke_session
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME

PROJECT=UUID('05460961-f12e-4fe7-ba6f-3e36e27bd23d')
OUT=Path('/app/data/qa/request12-20260919');OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','status','export','ppt','resume','sections','fix-feedback']);args=parser.parse_args()
pool.open();token=None
try:
    with tenant_context(system=True),connection() as c:
        account=c.execute("SELECT a.id FROM accounts a JOIN project_members m ON m.account_id=a.id WHERE a.email='user01@kodame.local' AND m.project_id=%s AND a.is_active",(PROJECT,)).fetchone()
        assert account
    token,_=create_session(account['id'],Request({'type':'http','headers':[(b'user-agent',b'ODAME authorized request12 QA')],'client':('127.0.0.1',0)}))
    with connection() as c,c.transaction():
        c.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '30 minutes' WHERE token_hash=%s",(PROJECT,hash_session_token(token)))
    with httpx.Client(base_url='http://kodame-redesign-web',cookies={SESSION_COOKIE_NAME:token},timeout=120,
            headers={'X-ODAME-Account':str(account['id']),'X-ODAME-Project':str(PROJECT)}) as client:
        def get(path):
            r=client.get('/api/v2/'+path);r.raise_for_status();return r.json()
        def post(path,payload=None):
            r=client.post('/api/v2/'+path,json=payload or {})
            if r.is_error:raise RuntimeError(f'{r.status_code}: {r.text[:1200]}')
            return r.json()
        if args.action=='start':
            started=post('report/generate-all');print(json.dumps(started),flush=True)
            for _ in range(90):
                status=get('report/generation/latest')
                if status['completed_sections']>=1:break
                time.sleep(1)
            cancelled=post(f"report/generation/{started['id']}/cancel")
            for _ in range(240):
                status=get('report/generation/latest')
                if status['status'] not in ['queued','running']:break
                time.sleep(2)
            assert status['status']=='cancelled',status
            sections=get('report/sections')
            rows=sections if isinstance(sections,list) else sections['items']
            saved={s['part_id']:hashlib.sha256(s['content'].encode()).hexdigest() for s in rows if s.get('content')}
            resumed=post(f"report/generation/{started['id']}/resume")
            assert resumed['preserved_sections']>=1,resumed
            result={'started':started,'cancelled':status,'saved_hashes':saved,'resumed':resumed}
            (OUT/'cancel-resume.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)
        elif args.action=='status':
            for key,path in [('generation','report/generation/latest'),('hwpx','report/exports/latest'),('ppt','report/presentations/latest')]:
                data=get(path);(OUT/(key+'-latest.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({key:{k:v for k,v in data.items() if k in ['id','status','completed_sections','failed_sections','current_part_id','message','error_message','model','progress','stage','download_url']}},ensure_ascii=False),flush=True)
        elif args.action=='sections':
            data=get('report/sections');(OUT/'sections.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            rows=data if isinstance(data,list) else data['items']
            print(json.dumps([{k:s.get(k) for k in ['part_id','status','quality_score','error_message']} for s in rows],ensure_ascii=False),flush=True)
        elif args.action=='fix-feedback':
            instruction='현재 사업개요의 사업기간은 2022.04.01~2029.03.31입니다. 환류과제의 2028년 말(전체 사업 종료 시점)이라는 표현은 사업기간과 충돌합니다. 2028년 말이 제안된 완료기한이면 제안으로 명시하고, 전체 사업 종료일로 단정하지 마세요. 또한 아직 실시·합의되지 않은 워크숍, 이관, 확약서 징구, 담당자와 일정은 실시 사실이 아니라 제안으로 분명히 표현하세요. 기존 3개 과제의 근거와 구분·제언·이해관계자·선정 사유·우선순위·완료기한·점검주기·후속 확인자료 필드는 보존하여 수정하세요. 새로운 사업 사실은 만들지 마세요.'
            print(json.dumps(post('report/sections/feedback/generate',{'instruction':instruction}),ensure_ascii=False),flush=True)
        elif args.action=='resume':
            run=get('report/generation/latest');print(json.dumps(post(f"report/generation/{run['id']}/resume"),ensure_ascii=False))
        else:
            path='report/exports' if args.action=='export' else 'report/presentations'
            print(json.dumps(post(path,{'slide_count':15} if args.action=='ppt' else {}),ensure_ascii=False),flush=True)
finally:
    if token:revoke_session(token)
    pool.close()
