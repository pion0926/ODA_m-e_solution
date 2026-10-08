"""Read saved user01 report, run current exporters, renderable local QA only."""
from pathlib import Path
import json
from kodame_intake.db import pool,tenant_context
from kodame_intake.submission_api import download_submission,KINDS
out=Path('/app/data/qa/request12-20260919/offline');out.mkdir(parents=True,exist_ok=True)
pool.open()
try:
    with tenant_context('05460961-f12e-4fe7-ba6f-3e36e27bd23d'):
        for kind,(filename,_) in KINDS.items():
            response=download_submission(kind)
            target=out/(kind+'.'+kind.split('-')[-1]);target.write_bytes(response.body)
            print(json.dumps({'kind':kind,'bytes':len(response.body),'file':str(target)},ensure_ascii=False),flush=True)
finally:pool.close()
