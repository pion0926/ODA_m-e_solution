"""Small local API load probe; no AI, private documents or production traffic."""
import asyncio,json,os,time,statistics
from pathlib import Path
import httpx
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
accounts=json.loads(Path('/qa/synthetic-accounts.json').read_text())
async def main():
    results=[]
    async with httpx.AsyncClient(base_url='http://kodame-redesign-api:8100',timeout=30) as client:
        response=await client.post('/api/v2/auth/login',json=accounts['logins'][0]);response.raise_for_status()
        semaphore=asyncio.Semaphore(8)
        async def run(index):
            async with semaphore:
                start=time.monotonic()
                path=('/api/v2/dashboard','/api/v2/pdm','/api/v2/intake/jobs','/healthz')[index%4]
                r=await client.get(path)
                results.append({'path':path,'status':r.status_code,'ms':round((time.monotonic()-start)*1000,2)})
                assert r.status_code==200,(path,r.status_code,r.text[:200])
                assert r.headers.get('x-request-id')
        await asyncio.gather(*(run(i) for i in range(80)))
    durations=sorted(r['ms'] for r in results)
    report={'status':'passed','requests':len(results),'concurrency':8,'median_ms':statistics.median(durations),
            'p95_ms':durations[int(.95*len(durations))-1],'max_ms':max(durations),'scope':'local synthetic 4-document project; excludes AI and large-project load'}
    Path('/qa/performance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
asyncio.run(main())
