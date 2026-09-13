"""Scoped KNUT correction via public API; retain before/after evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import httpx
from report_outline import canonical_narrative_outline_text

ROOT = Path('/workspace/output/knut-overview-label-20260912')


def save(name, data):
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'export', 'status'])
    args = parser.parse_args()
    with httpx.Client(base_url='http://kodame-redesign-api:8100/api/v2', timeout=180) as client:
        r = client.post('/auth/login', json={'email': 'knut', 'password': os.environ['KNUT_QA_PASSWORD']})
        r.raise_for_status()
        assert r.json()['project']['id'] == 'ee8b8006-96eb-4f69-9778-233c42f6f009'
        if args.action == 'prepare':
            r = client.get('/report/sections'); r.raise_for_status()
            before = r.json(); save('sections-before.json', before)
            item = client.get('/report/sections/working-factors'); item.raise_for_status()
            old = item.json()['content']
            fixed = canonical_narrative_outline_text('working-factors', old)
            # One-off cleanup of prefixes already joined by the first QA
            # candidate; no project-specific rule is added to production.
            fixed = fixed.replace('(역할 분담·재정 자립 예산 집행 증빙 강화)', '(재정 자립 예산 집행 증빙 강화)')
            fixed = fixed.replace('(제도적 성과·직역 법적 지위 및 업무 범위 명문화)', '(직역 법적 지위 및 업무 범위 명문화)')
            if old != fixed:
                r = client.put('/report/sections/working-factors', json={'content': fixed})
                r.raise_for_status()
            r = client.get('/report/sections'); r.raise_for_status()
            after = r.json(); save('sections-after.json', after)
            old_map = {i['part_id']: i['content'] for i in before['items']}
            changed = [i['part_id'] for i in after['items'] if i['content'] != old_map[i['part_id']]]
            assert set(changed) <= {'working-factors'}, changed
            print(json.dumps({'changed': changed, 'before_chars': len(old), 'after_chars': len(fixed)}))
        elif args.action == 'export':
            r = client.post('/report/exports', json={}); r.raise_for_status()
            save('export-start.json', r.json()); print(r.text)
        else:
            start = json.loads((ROOT/'export-start.json').read_text())
            r = client.get('/report/exports/' + start['id']); r.raise_for_status()
            result = r.json(); save('export-result.json', result)
            print(json.dumps({k:result.get(k) for k in ('id','status','progress','message','error_message')}, ensure_ascii=False))
            if result['status'] == 'completed':
                r = client.get(result['download_url'].removeprefix('/api/v2')); r.raise_for_status()
                path = ROOT / 'KNUT-overview-label-fixed.hwpx'; path.write_bytes(r.content)
                print(json.dumps({'file':str(path), 'sha256': hashlib.sha256(r.content).hexdigest(), 'rhwp_pages':result['validation'].get('rhwp_page_count')}))


if __name__ == '__main__':
    main()
