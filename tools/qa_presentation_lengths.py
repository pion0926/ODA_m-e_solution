"""Live acceptance check for the two presentation choices. Run locally only."""
import json
import time
import sys
from pathlib import Path
import urllib.request
import urllib.error
import http.cookiejar


class Response:
    def __init__(self, response):
        self.status_code = response.code
        self.content = response.read()
        self.text = self.content.decode('utf-8', errors='replace')

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}: {self.text[:500]}')


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, path):
        return self.request(path)

    def post(self, path, json):
        return self.request(path, json)

    def request(self, path, payload=None):
        request = urllib.request.Request('http://127.0.0.1:8002'+path,
                    data=json.dumps(payload).encode() if payload is not None else None,
                    headers={'Content-Type': 'application/json'})
        try:
            return Response(self.opener.open(request, timeout=60))
        except urllib.error.HTTPError as exc:
            return Response(exc)

root = Path(__file__).resolve().parents[1]
out = root / 'output/presentation-reference-20260906'
out.mkdir(parents=True, exist_ok=True)
with Client() as client:
    response = client.post('/api/v2/auth/login', json={'email': 'admin@kodame.local', 'password': 'admin'})
    response.raise_for_status()
    print('Authenticated for local acceptance check', flush=True)
    bad = client.post('/api/v2/report/presentations', json={'slide_count': 50})
    assert bad.status_code == 422, bad.text
    print('50-page option rejected: HTTP 422', flush=True)
    for count in ([int(v) for v in sys.argv[1:]] or [15, 30]):
        started = client.post('/api/v2/report/presentations', json={'slide_count': count})
        started.raise_for_status()
        job = started.json()
        print(json.dumps(job, ensure_ascii=False), flush=True)
        previous = None
        deadline = time.monotonic()+3600
        while time.monotonic() < deadline:
            status = client.get(f"/api/v2/report/presentations/{job['id']}").json()
            message = (status.get('status'), status.get('message'), status.get('error_message'))
            if message != previous:
                print(json.dumps({'count': count, 'status': status.get('status'), 'progress': status.get('progress'),
                                  'message': status.get('message'), 'error': status.get('error_message')}, ensure_ascii=False), flush=True)
                previous = message
            if status.get('status') == 'completed':
                assert status['slide_count'] == count
                download = client.get(status['download_url'])
                download.raise_for_status()
                (out/f'ODAME-{count}pages.pptx').write_bytes(download.content)
                (out/f'ODAME-{count}pages-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'Completed {count}: {out}', flush=True)
                break
            if status.get('status') == 'failed':
                raise RuntimeError(status.get('error_message'))
            time.sleep(8)
        else:
            raise TimeoutError('Live generation exceeded 60 minutes')
