"""Materialize authenticated Drive connector file references, preserving provenance."""
import hashlib,json,re,sys,urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

root=Path(__file__).resolve().parents[1]
target=root/'samples/knut-production-20260920'
target.mkdir(parents=True,exist_ok=True)
batch=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
def download(row):
    folder=row['relative_path'][:-len(row['title'])].strip('/')
    name=re.sub(r'[<>:"/\\|?*]','_',row['title']).rstrip('. ')
    if row['mime_type']=='application/pdf' and not name.lower().endswith('.pdf'):name+='.pdf'
    path=(target/folder/name).resolve()
    assert path.is_relative_to(target.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    expected=int(row['size'])
    if not path.is_file() or path.stat().st_size!=expected:
        request=urllib.request.Request(row['download_url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=180) as response:data=response.read()
        assert len(data)==expected,(row['id'],len(data),expected)
        temporary=path.with_suffix(path.suffix+'.part');temporary.write_bytes(data);temporary.replace(path)
    return {k:v for k,v in row.items() if k!='download_url'}|{'local_path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(download,batch))
manifest=target/'download-manifest.json'
existing=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
combined={r['id']:r for r in existing+results}
manifest.write_text(json.dumps(list(combined.values()),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'batch':len(results),'downloaded':len(combined),'bytes':sum(int(r['size']) for r in combined.values())}))
