"""HTTP auth/preview/concurrency checks; no LLM and no successful content write."""
import base64
import json
import os
from pathlib import Path
import httpx

ROOT = Path('/workspace/output/section-preview-20260912')


def main():
    results = {}
    with httpx.Client(base_url='http://kodame-redesign-api:8100/api/v2',timeout=90) as client:
        r = client.post('/report/sections/working-factors/preview',json={'content':'미리보기 시험'})
        assert r.status_code == 401, r.text
        results['unauthenticated'] = r.status_code
        r = client.post('/auth/login',json={'email':'knut','password':os.environ['KNUT_QA_PASSWORD']})
        r.raise_for_status()
        assert r.json()['project']['id'] == 'ee8b8006-96eb-4f69-9778-233c42f6f009'
        before = client.get('/report/sections').json()['items']
        item = next(row for row in before if row['part_id']=='working-factors')
        r = client.post('/report/sections/working-factors/preview',json={'content':item['content']})
        r.raise_for_status()
        assert r.headers['cache-control'] == 'no-store'
        results['preview_status'] = r.status_code
        results['preview_ms'] = r.json()['render_ms']
        r = client.post('/report/sections/not-a-section/preview',json={'content':'test'})
        assert r.status_code == 404
        results['unknown_section'] = r.status_code
        r = client.put('/report/sections/working-factors',json={'content':item['content'],'expected_updated_at':'2000-01-01T00:00:00+00:00'})
        assert r.status_code == 409, r.text
        results['stale_save_rejected'] = r.status_code
        after = client.get('/report/sections').json()['items']
        columns = lambda rows:{r['part_id']:(r['content'],r['updated_at']) for r in rows}
        assert columns(before)==columns(after)
        results['all_27_unchanged'] = True
        baseline = json.loads(Path('/workspace/output/knut-overview-label-20260912/sections-after.json').read_text())['items']
        assert {r['part_id']:r['content'] for r in baseline} == {r['part_id']:r['content'] for r in after}
        results['all_content_matches_previous_final_report'] = True
        ROOT.mkdir(parents=True,exist_ok=True)
        (ROOT/'api-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':
    main()
