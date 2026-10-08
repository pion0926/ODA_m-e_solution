"""Authenticated development-only presentation acceptance run; no source edits."""
import json
import sys
from pathlib import Path
import httpx
from kodame_intake.settings import BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD

STATE = Path('/app/data/qa_astra_20260916_private.json')
BASE = 'http://127.0.0.1:8100'


def call(c, method, url, **kwargs):
    r = c.request(method, url, **kwargs)
    r.raise_for_status()
    return r.json()


with httpx.Client(base_url=BASE, timeout=60) as c:
    if not STATE.exists():
        call(c, 'POST', '/api/v2/auth/login', json={'email':BOOTSTRAP_ADMIN_EMAIL,'password':BOOTSTRAP_ADMIN_PASSWORD})
        account = call(c, 'POST', '/api/v2/admin/accounts', json={
            'username':'pptqa0916', 'display_name':'PPT 검증 0916',
            'project_id':'ee8b8006-96eb-4f69-9778-233c42f6f009'})
        state = {'username':'pptqa0916', 'password':account['initial_password']}
        STATE.write_text(json.dumps(state), encoding='utf-8')
        STATE.chmod(0o600)
    state = json.loads(STATE.read_text())
    call(c, 'POST', '/api/v2/auth/login', json={'email':state['username'],'password':state['password']})
    if sys.argv[1] == 'start':
        count = int(sys.argv[2])
        result = call(c, 'POST', '/api/v2/report/presentations', json={'slide_count':count})
        state[str(count)] = result['id']
        STATE.write_text(json.dumps(state), encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    else:
        for count in ('15','30'):
            if count in state:
                result = call(c,'GET',f'/api/v2/report/presentations/{state[count]}')
                print(json.dumps(result,ensure_ascii=False))
