"""Check session cookie survives API restart, only against isolated QA."""
import json,os,sys
from pathlib import Path
import httpx
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
path=Path('/qa/session-continuity.json')
with httpx.Client(base_url='http://kodame-redesign-api:8100/api/v2/',timeout=30) as client:
    if sys.argv[1]=='capture':
        login=json.loads(Path('/qa/synthetic-accounts.json').read_text())['logins'][0]
        r=client.post('auth/login',json=login);r.raise_for_status()
        body=client.get('auth/me').json()
        path.write_text(json.dumps({'cookies':dict(client.cookies),'account':body['account']['id'],'project':body['project']['id']}))
    else:
        saved=json.loads(path.read_text());client.cookies.update(saved['cookies'])
        r=client.get('auth/me');r.raise_for_status();body=r.json()
        assert body['account']['id']==saved['account'] and body['project']['id']==saved['project']
        print('PASS existing session authenticates after API restart without another login')
