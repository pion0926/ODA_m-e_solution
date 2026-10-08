"""Synthetic-only PostgreSQL, resource isolation and workflow acceptance checks."""
import json, os, time, uuid, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from types import SimpleNamespace
from psycopg.types.json import Jsonb
import psycopg
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.ai.global_budget import reserve,settle
from kodame_intake.ai.job_budget import BudgetExceeded
from kodame_intake.workflow_queue import enqueue,claim_task,finish_task
from kodame_intake.evaluation_versions import current_bundle,approve,compare
from kodame_intake.project_lifecycle import capture_input_snapshot
from kodame_intake.translation_jobs import request_translation,run_translation
from kodame_intake.parse_sandbox import parse_isolated,ParseLimitExceeded
checks=[]; metrics={}
def check(ok,label):
    assert ok,label
    checks.append(label); print('PASS '+label,flush=True)
pool.open(wait=True)
info=json.loads(Path('/qa/synthetic-accounts.json').read_text())
project=info['projects'][1]['id']
with tenant_context(project),connection() as conn:
    assert conn.execute('SELECT name FROM projects WHERE id=%s',(project,)).fetchone()['name'].startswith('합성 QA ')
    actor=conn.execute('SELECT account_id FROM project_members WHERE project_id=%s',(project,)).fetchone()['account_id']
key='qa-budget-'+uuid.uuid4().hex
try:
    with patch.dict(os.environ,{'AI_GLOBAL_IN_FLIGHT':'4'}):
        def book(n):
            return reserve(key,'qa-concurrent','test',10,.01)
        with ThreadPoolExecutor(max_workers=16) as executor:
            booked=[x for x in executor.map(book,range(24)) if x]
        check(len(booked)==4,'24 concurrent reservations admit exactly 4 global requests')
        settle(booked[0],{'usage':{'total_tokens':3,'cost':.001}})
        with connection() as conn:
            row=conn.execute('SELECT tokens,cost_usd,usage_confirmed FROM ai_request_reservations WHERE id=%s',(booked[0],)).fetchone()
        check(row['tokens']==3 and row['usage_confirmed'],'actual provider usage replaces conservative reservation')
    with patch.dict(os.environ,{'AI_JOB_REQUESTS':'4'}):
        try: reserve(key,'qa-concurrent','test',1,.001)
        except BudgetExceeded: check(True,'job attempt budget includes previous and in-flight calls')
        else: raise AssertionError('Job budget ignored')
finally:
    with connection() as conn: conn.execute('DELETE FROM ai_request_reservations WHERE key_hash=%s',(key,))

with tenant_context(project,account_id=actor):
    # Save a synthetic report bundle; this tests approval mechanics, not AI quality.
    with connection() as conn:
        conn.execute("INSERT INTO intake_documents(id,original_name,stored_path,extension,size_bytes,sha256,status) VALUES (%s,'synthetic-approval.txt','/qa/synthetic','.txt',1,%s,'completed')",(uuid.uuid4(),'a'*64))
        snapshot=capture_input_snapshot(conn)
        conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count,completed_at,input_snapshot) VALUES (%s,'completed','synthetic-test',1,now(),%s)",(uuid.uuid4(),Jsonb(snapshot)))
        snapshot=capture_input_snapshot(conn)
        conn.execute("UPDATE report_sections SET content='합성 검토용 본문',status='draft',generated_at=now(),generation_metadata=%s",(Jsonb({'input_snapshot':snapshot}),))
        current=current_bundle(conn)
    with connection() as conn,conn.transaction():
        approved=approve(conn,SimpleNamespace(revision=current['revision'],source_fidelity=True,conclusion_validity=True,note='합성 출처·결론 검토'))
    check(approved['status']=='approved','human source and conclusion review saves immutable input/result bundle')
    try:
        with connection() as conn:
            conn.execute("UPDATE evaluation_versions SET payload='{}' WHERE id=%s",(approved['id'],))
    except psycopg.Error: check(True,'database rejects editing approved payload')
    else: raise AssertionError('Approved version was mutable')
    with connection() as conn:
        conn.execute("UPDATE report_sections SET content=content||' 변경' WHERE part_id='conclusion'")
        changed=current_bundle(conn)
    check(changed['revision']!=current['revision'] and bool(compare(current['payload'],changed['payload'])),'edited conclusion invalidates current approval with a visible difference')
    try:
        with connection() as conn,conn.transaction():
            approve(conn,SimpleNamespace(revision=current['revision'],source_fidelity=True,conclusion_validity=True,note='stale'))
    except Exception as exc: check(getattr(exc,'status_code',None)==409,'stale approval rejected transactionally')
    else: raise AssertionError('Stale approval allowed')
    views={'dashboard':{'project':{'name':'합성 번역 시험'}}}
    with patch('kodame_intake.translation_jobs._cached_translation',return_value=None):
        queued=request_translation(views,'en','ko')
        again=request_translation(views,'en','ko')
    check(queued['translation_status']=='queued' and queued['job_id']==again['job_id'] and queued['views']==views,'uncached reads return original immediately and deduplicate durable translation')
    with patch('kodame_intake.translation_jobs.localize_project_views',return_value={}):
        run_translation(queued['job_id'])
    with connection() as conn:
        task=conn.execute("SELECT * FROM workflow_tasks WHERE kind='translation' AND arguments->>0=%s",(queued['job_id'],)).fetchone()
        check(finish_task(conn,task)=='completed','translation receipt and durable task agree after execution')
        conn.execute("DELETE FROM workflow_tasks WHERE id=%s",(task['id'],))

with tenant_context(info['projects'][0]['id']),connection() as conn:
    check(not conn.execute('SELECT 1 FROM evaluation_versions WHERE id=%s',(approved['id'],)).fetchone(),'approval bundles remain isolated by tenant RLS')

# Claims run in a rollback-only transaction so no other QA receipt is changed.
with tenant_context(system=True),connection() as conn:
    try:
        with conn.transaction():
            conn.execute("UPDATE workflow_tasks SET status='cancelled' WHERE status IN ('running','queued')")
            for n in range(3):
                conn.execute("INSERT INTO workflow_tasks(id,project_id,kind,queue,arguments,model) VALUES (%s,%s,'translation','analysis','[]','test')",
                    (uuid.uuid4(),info['projects'][n%2]['id']))
            first=claim_task(conn,'qa-a',0,'analysis'); second=claim_task(conn,'qa-b',1,'analysis'); third=claim_task(conn,'qa-c',2,'analysis')
            check(first['project_id']!=second['project_id'] and third is None,'two worker slots process distinct projects and exclude overlapping project writes')
            raise psycopg.Rollback()
    except psycopg.Rollback: pass

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)/'large-synthetic.pdf'
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for number in range(240):
        page=writer.add_blank_page(600,800)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(('BT /F1 10 Tf 10 700 Td ('+f'Synthetic page {number} annual outcome 54. '*30+') Tj ET').encode())
        page[NameObject('/Contents')]=stream
    writer.write(path)
    started=time.monotonic()
    with patch.dict(os.environ,{'PARSER_ISOLATION':'true'}),ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _:parse_isolated(path,'.pdf'),range(4)))
    metrics['four_240_page_pdfs_seconds']=round(time.monotonic()-started,2)
    check(all('Synthetic page 239' in text for text,method in results),'four isolated 240-page PDF parses retain final-page text')
    with patch.dict(os.environ,{'PARSER_ISOLATION':'true','PARSER_TIMEOUT_SECONDS':'0'}):
        try: parse_isolated(path,'.pdf')
        except ParseLimitExceeded: check(True,'parser deadline terminates child process and returns recoverable error')
        else: raise AssertionError('Parser deadline ignored')
    bad=Path(temporary)/'bad.pdf';bad.write_bytes(b'corrupt pdf')
    try: parse_isolated(bad,'.pdf')
    except Exception: check(True,'corrupt parser input fails within isolated process')
    else: raise AssertionError('Corrupt document accepted')
result={'status':'passed','checks':checks,'metrics':metrics}
Path('/qa/runtime-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
pool.close()
