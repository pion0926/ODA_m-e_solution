"""Use the production user's actual HTTPS API for the authorized workflow."""
import argparse,json,os,re,sys,time
from pathlib import Path
import httpx

parser=argparse.ArgumentParser();parser.add_argument('action',choices=['upload','status','snapshot','pdm','evaluate','generate','resume','section','export','download','submissions','retry']);parser.add_argument('--id');args=parser.parse_args()
assert os.environ['SESSION_COOKIE_NAME']=='kodame_production_session'
credentials=json.loads(Path('/tmp/production-knut-private.json').read_text(encoding='utf-8'))
out=Path('/app/data/qa/production-knut-20260920');out.mkdir(parents=True,exist_ok=True)
def save(name,value):
 (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
with httpx.Client(base_url='https://app.kodame.kr',timeout=600) as client:
 def call(method,path,payload=None,**kwargs):
  r=client.request(method,'/api/v2/'+path,json=payload,**kwargs)
  if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:900]}')
  return r
 call('POST','auth/login',{'email':credentials['username'],'password':credentials['password']})
 try:
  call('PUT',f"account/projects/{credentials['project_id']}/select")
  client.headers.update({'X-ODAME-Account':credentials['account_id'],'X-ODAME-Project':credentials['project_id']})
  if args.action=='upload':
   root=Path('/tmp/knut-source');manifest=json.loads((root/'download-manifest.json').read_text(encoding='utf-8'))
   # Keep the explicitly named latest PDM when duplicate bytes are deduplicated.
   manifest.sort(key=lambda r:(not ('최신 PDM' in r['title']),not ('사업계획서' in r['title']),r['relative_path']))
   record_path=out/'uploads.json'
   results=json.loads(record_path.read_text(encoding='utf-8')) if record_path.exists() else []
   uploaded={r['drive_id'] for r in results if not r['response'].get('rejected_count')}
   for row in manifest:
    if row['id'] in uploaded:continue
    relative=row['local_path'].replace('\\','/').split('samples/knut-production-20260920/',1)[1]
    path=(root/relative).resolve();assert path.is_relative_to(root.resolve())
    folder=row['relative_path'][:-len(row['title'])].strip('/')
    name=re.sub(r'[<>:"/\\|?*]','_',folder+'__'+path.name)
    for attempt in range(4):
     with path.open('rb') as stream:
      r=client.post('/api/v2/intake/uploads',files={'files':(name,stream,row['mime_type'])})
     if r.status_code not in (502,503,504,520,522,524) or attempt==3:break
     time.sleep(2**attempt)
    r.raise_for_status();response=r.json()
    results.append({'drive_id':row['id'],'source':row['relative_path'],'response':response});save('uploads',results)
    if response['rejected_count']:raise RuntimeError(json.dumps(response['rejected'],ensure_ascii=False))
    print(json.dumps({'uploaded':len(results),'total':len(manifest),'deduplicated':response['accepted'][0]['deduplicated']},ensure_ascii=False),flush=True)
   print(json.dumps({'source_files':len(results),'unique_documents':len({r['response']['accepted'][0]['id'] for r in results})}),flush=True)
  elif args.action=='status':
   for key,path in [('intake','intake/jobs?limit=200'),('evaluation','evaluations/status'),('generation','report/generation/latest'),('export','report/exports/latest'),('lifecycle','project/lifecycle')]:
    data=call('GET',path).json();save(key,data)
    if key=='intake':result={'total':data['total'],'counts':data['status_counts'],'errors':[{'id':r['id'],'name':r.get('file_name',r.get('name')),'status':r['status'],'message':r.get('error_message')} for r in data['items'] if r['status'] in ['failed','retry','waiting_llm']]}
    else:result={k:v for k,v in data.items() if k in ['id','run_id','status','phase','progress','message','error_message','completed_sections','failed_sections','document_count','completed_document_count','can_start','evaluation_current','report_current','download_url']}
    print(json.dumps({key:result},ensure_ascii=False),flush=True)
  elif args.action in ['download','snapshot']:
   if args.action=='download':
    latest=call('GET','report/exports/latest').json();assert latest['status']=='completed'
    r=client.get(latest['download_url']);r.raise_for_status();(out/'knut-report.hwpx').write_bytes(r.content)
    print(json.dumps({'downloaded':len(r.content),'export':latest['id']}),flush=True)
   for key,path in [('evaluations','evaluations'),('pdm','pdm'),('overview','project-overview'),('sections','report/sections'),('dashboard','dashboard')]:save(key,call('GET',path).json())
   print(json.dumps({'snapshot':'saved'}),flush=True)
  elif args.action=='submissions':
   import zipfile,io
   rows=[]
   for kind in ['grade-xlsx','grade-hwpx','lessons-pptx','lessons-hwpx','feedback-xlsx','feedback-pptx']:
    r=call('GET','report/submissions/'+kind)
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:assert archive.testzip() is None
    name='knut-'+kind+'.'+kind.rsplit('-',1)[1];(out/name).write_bytes(r.content)
    rows.append({'kind':kind,'file':name,'bytes':len(r.content),'status':r.status_code})
    print(json.dumps(rows[-1]),flush=True)
   save('submissions',rows)
  else:
   if args.action in ['resume','section']:assert args.id,'Id required'
   paths={'pdm':'pdm/refresh','evaluate':'evaluations','generate':'report/generate-all','resume':f'report/generation/{args.id}/resume','section':f'report/sections/{args.id}/generate','export':'report/exports','retry':f'intake/jobs/{args.id}/retry'}
   result=call('POST',paths[args.action],{}).json();save(args.action+'-started',result);print(json.dumps(result,ensure_ascii=False),flush=True)
 finally:
  call('POST','auth/logout')
