"""Verify all requested Drive originals against accepted API upload hashes."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'output/knut-e2e-20260911'
manifest=json.loads((root/'drive-manifest.json').read_text(encoding='utf-8'))
uploads=json.loads((root/'uploads.json').read_text(encoding='utf-8'))
rows=[]
for f in manifest:
    upload=next(x for x in uploads if x['drive_id']==f['id'])['response']['accepted'][0]
    path=next((root/'source').glob(f['id']+'__*'))
    if f['id']=='1FHC239dlqLSTzM-XyzMFkLTuJ8CcPHjl':
        path=root/'source/zip-verified.download'
        upload=json.loads((root/'zip-corrected-upload.json').read_text(encoding='utf-8'))['accepted'][0]
    data=path.read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    valid=len(data)==int(f['size'])==upload['size_bytes'] and sha==upload['sha256']
    rows.append({'drive_id':f['id'],'title':f['title'],'document_id':upload['id'],'bytes':len(data),'sha256':sha,'pass':valid})
(root/'input-integrity.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'count':len(rows),'bytes':sum(x['bytes'] for x in rows),'passed':sum(x['pass'] for x in rows)}))
assert len(rows)==73 and all(x['pass'] for x in rows)
