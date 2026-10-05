"""Short-lived, same-project account for authorized production manual screenshots."""
import json,secrets,sys
from pathlib import Path
import httpx

root=json.loads(Path('/tmp/production-knut-private.json').read_text())
file=Path('/tmp/manual-capture-private.json')
with httpx.Client(base_url='https://app.kodame.kr',timeout=60) as client:
    def call(method,path,data=None):
        response=client.request(method,'/api/v2/'+path,json=data)
        response.raise_for_status()
        return response.json() if response.status_code!=204 else None
    call('POST','auth/login',{'email':'admin','password':root['admin_password']})
    try:
        if sys.argv[1]=='create':
            assert not file.exists(),'Capture account already exists; reuse its stored credentials'
            data={'username':'manual.capture.20260920','password':secrets.token_urlsafe(24),
                  'display_name':'매뉴얼 사용자','project_id':root['project_id']}
            account=call('POST','admin/accounts',data)
            data['account_id']=account['id']
            file.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            file.chmod(0o600)
            print(json.dumps({'temporary_account':account['id'],'project':root['project_id'],'created':True}))
        elif sys.argv[1]=='activate':
            data=json.loads(file.read_text())
            call('PUT',f"admin/accounts/{data['account_id']}/status",{'is_active':True})
            call('PUT',f"admin/accounts/{data['account_id']}/projects",{
                'project_ids':[data['project_id']],'expected_project_ids':[]})
            print(json.dumps({'temporary_account':data['account_id'],'activated_for_capture':True}))
        elif sys.argv[1]=='disable':
            data=json.loads(file.read_text())
            call('PUT',f"admin/accounts/{data['account_id']}/status",{'is_active':False})
            result=call('GET','admin/accounts')
            rows=result if isinstance(result,list) else result['accounts']
            item=next(a for a in rows if a['id']==data['account_id'])
            ids=[p['id'] for p in item.get('projects',[])]
            if ids:
                call('PUT',f"admin/accounts/{data['account_id']}/projects",{
                    'project_ids':[],'expected_project_ids':ids})
            print(json.dumps({'temporary_account':data['account_id'],'disabled':True,'project_access_removed':True}))
    finally:
        call('POST','auth/logout')
