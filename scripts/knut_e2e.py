"""KNUT end-to-end QA using the public service API (no database writes)."""
import argparse
import json
import os
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1] / 'output/knut-e2e-20260911'
BASE = os.environ.get('KNUT_QA_BASE', 'http://127.0.0.1:8002/api/v2')

def save(name, data):
    (ROOT / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['snapshot', 'upload', 'post', 'get', 'download', 'repair-zip', 'model'])
    parser.add_argument('path', nargs='?', default='')
    parser.add_argument('--instruction', default='')
    args = parser.parse_args()
    with httpx.Client(base_url=BASE, timeout=180) as c:
        r=c.post('/auth/login', json={'email':'knut','password':os.environ['KNUT_QA_PASSWORD']})
        r.raise_for_status()
        me=r.json()
        assert me['project']['id']=='ee8b8006-96eb-4f69-9778-233c42f6f009', me
        if args.action=='model':
            r=c.put('/account/settings',json={'llm_model':args.path})
            print(r.status_code,r.text)
            save('model-selection',r.json())
        elif args.action=='snapshot':
            data={'auth':me}
            for endpoint in ['dashboard','intake/jobs','pdm','project-overview','evaluations','evaluations/status','report/sections','report/generation/latest','report/exports/latest']:
                response=c.get('/'+endpoint)
                data[endpoint]={'status_code':response.status_code,'body':response.json()}
            save(args.path or 'snapshot',data)
            print(json.dumps({k:len(str(v)) for k,v in data.items()}))
        elif args.action=='repair-zip':
            p=ROOT/'source/zip-verified.download'
            assert p.stat().st_size==29350959
            import zipfile
            with zipfile.ZipFile(p) as archive: assert archive.testzip() is None
            with p.open('rb') as stream:
                r=c.post('/intake/uploads',files={'files':('교육과정_교재 외상학_2026-06-23_교통대.zip',stream,'application/zip')})
            r.raise_for_status()
            save('zip-corrected-upload',r.json())
            print(r.status_code,r.text)
        elif args.action=='upload':
            manifest_path=ROOT/'downloads.json'
            if manifest_path.exists():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            else:
                manifest=[]
                for f in json.loads((ROOT/'drive-manifest.json').read_text(encoding='utf-8')):
                    matches=list((ROOT/'source').glob(f['id']+'__*'))
                    if len(matches)==1 and matches[0].stat().st_size==int(f['size']):
                        manifest.append({'id':f['id'],'path':str(matches[0]),'name':matches[0].name.split('__',1)[1]})
            result_path=ROOT/'uploads.json'
            results=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else []
            done={x['drive_id'] for x in results if x['status_code']==202}
            for f in manifest:
                if f['id'] in done: continue
                p=ROOT/'source'/Path(f['path']).name
                expected=next(x for x in json.loads((ROOT/'drive-manifest.json').read_text(encoding='utf-8')) if x['id']==f['id'])
                if p.stat().st_size!=int(expected['size']):
                    raise ValueError('Incomplete download: '+f['name'])
                with p.open('rb') as stream:
                    response=c.post('/intake/uploads',files={'files':(f['name'],stream,'application/octet-stream')})
                results.append({'drive_id':f['id'],'name':f['name'],'status_code':response.status_code,'response':response.json()})
                save('uploads',results)
                print(json.dumps({'file':f['name'],'status_code':response.status_code},ensure_ascii=False),flush=True)
        elif args.action=='download':
            r=c.get(args.path); r.raise_for_status()
            (ROOT/'KNUT-final-report.hwpx').write_bytes(r.content)
            print('downloaded',len(r.content))
        else:
            r=c.post(args.path,json={'instruction':args.instruction} if args.instruction else {}) if args.action=='post' else c.get(args.path)
            print(r.status_code, r.text)
            save(args.path.strip('/').replace('/','_'),{'status_code':r.status_code,'body':r.json()})

if __name__=='__main__': main()
