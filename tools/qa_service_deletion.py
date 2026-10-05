"""Delete only a project/account/file created by this run in isolated QA."""
import json,os,uuid
from pathlib import Path
import httpx
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.workflow_queue import enqueue
pool.open(wait=True)
base='http://kodame-redesign-api:8100/api/v2/'
admin=httpx.Client(base_url=base,timeout=30)
assert admin.post('auth/login',json={'email':'admin','password':'qa-admin-local-only'}).status_code==200
tag=uuid.uuid4().hex[:8]
project=admin.post('admin/projects',json={'name':'합성 삭제 QA '+tag,'supported_locales':['ko'],'default_locale':'ko'}).json()
account=admin.post('admin/accounts',json={'username':'delete_'+tag,'display_name':'합성 삭제 QA','project_id':project['id']}).json()
user=httpx.Client(base_url=base,timeout=30)
assert user.post('auth/login',json={'email':'delete_'+tag,'password':account['initial_password']}).status_code==200
response=user.post('intake/uploads',params={'role':'project_plan'},files={'files':('삭제검증.txt',b'synthetic deletion fixture','text/plain')})
assert response.status_code==202,response.text
document=response.json()['accepted'][0]
assert user.post('intake/jobs/'+document['id']+'/cancel').status_code==202
route='admin/projects/'+project['id']
assert user.get(route+'/deletion-preview').status_code==403
preview=admin.get(route+'/deletion-preview').json()
payload={'name':preview['name'],'revision':preview['revision'],'confirmed':False}
assert admin.request('DELETE',route,json=payload).status_code==409
payload['confirmed']=True
assert admin.request('DELETE',route,json={**payload,'revision':'0'*64}).status_code==409
with tenant_context(project['id'],account_id=account['id']),connection() as conn:
    stored=Path(conn.execute('SELECT stored_path FROM intake_documents WHERE id=%s',(document['id'],)).fetchone()['stored_path'])
    assert stored.is_file()
    run=uuid.uuid4()
    conn.execute("INSERT INTO pdm_refresh_runs(id,status,model) VALUES (%s,'queued','google/gemini-3.5-flash-lite')",(run,))
    task=enqueue(conn,'pdm',[run,project['id'],'google/gemini-3.5-flash-lite'],'google/gemini-3.5-flash-lite')
assert admin.request('DELETE',route,json=payload).status_code==409
with tenant_context(project['id']),connection() as conn:
    conn.execute("UPDATE pdm_refresh_runs SET status='cancelled' WHERE id=%s",(run,))
    conn.execute("UPDATE workflow_tasks SET status='cancelled' WHERE id=%s",(task,))
response=admin.request('DELETE',route,json=payload)
assert response.status_code==200,response.text
assert response.json()['deleted'] and not response.json()['cleanup_pending']
assert not stored.exists()
with tenant_context(system=True),connection() as conn:
    for table,ident in [('projects',project['id']),('accounts',account['id']),('intake_documents',document['id']),('workflow_tasks',task)]:
        assert not conn.execute(f'SELECT 1 FROM {table} WHERE id=%s',(ident,)).fetchone(),table
assert user.get('auth/me').status_code==401
assert admin.get('auth/me').status_code==200
result={'status':'passed','checks':['project user cannot delete','explicit second confirmation enforced','stale deletion scope rejected','active task blocks deletion','DB/account/session/workflow cascade','original file removed; cleanup complete','administrator session remains valid']}
Path('/qa/deletion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
pool.close()
