"""Authorized production provisioning, with credentials supplied out of source."""
import json,os,sys
from pathlib import Path
import httpx
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.admin import reset_account_password
from kodame_intake.security import verify_password

assert os.environ['SESSION_COOKIE_NAME']=='kodame_production_session'
assert os.environ['OPENROUTER_REFERER']=='https://app.kodame.kr'
private=Path(sys.argv[1]);credentials=json.loads(private.read_text(encoding='utf-8-sig'))
pool.open()
with tenant_context(system=True),connection() as c:
 admin=c.execute("SELECT id,password_hash FROM accounts WHERE email='admin@kodame.local' AND is_admin AND is_active").fetchone()
 assert admin
if not verify_password(credentials['admin_password'],admin['password_hash']):reset_account_password(str(admin['id']),credentials['admin_password'])
pool.close()
with httpx.Client(base_url='https://app.kodame.kr',timeout=90) as client:
 def request(method,path,payload=None):
  r=client.request(method,'/api/v2/'+path,json=payload)
  if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:800]}')
  return r
 login=request('POST','auth/login',{'email':'admin','password':credentials['admin_password']})
 assert 'Secure' in login.headers.get('set-cookie','') and 'HttpOnly' in login.headers.get('set-cookie','')
 projects=request('GET','admin/projects').json()
 rows=projects if isinstance(projects,list) else projects['projects']
 matches=[p for p in rows if p['name']=='knut'];assert len(matches)<=1
 project=matches[0] if matches else request('POST','admin/projects',{'name':'knut','supported_locales':['ko'],'default_locale':'ko','account_ids':[]}).json()
 accounts=request('GET','admin/accounts').json();rows=accounts if isinstance(accounts,list) else accounts['accounts']
 matches=[a for a in rows if a['email']==credentials['username']+'@kodame.local'];assert len(matches)<=1
 account=matches[0] if matches else request('POST','admin/accounts',{'username':credentials['username'],'password':credentials['password'],'display_name':'KNUT 사용자','project_id':project['id']}).json()
 credentials.update(project_id=project['id'],account_id=account['id'])
 private.write_text(json.dumps(credentials,ensure_ascii=False,indent=2),encoding='utf-8')
 request('POST','auth/logout')
 user=request('POST','auth/login',{'email':credentials['username'],'password':credentials['password']}).json()
 selected=request('PUT',f"account/projects/{project['id']}/select").json()
 board=request('GET','dashboard').json()
 assert board['project']['name']=='knut'
 request('POST','auth/logout')
 print(json.dumps({'admin_password_changed':True,'public_login':'passed','secure_cookie':True,'project':project['id'],'account':account['id'],'username':credentials['username']},ensure_ascii=False))
