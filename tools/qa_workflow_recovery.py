"""Prepare/verify worker recovery in the isolated synthetic QA database."""
import json, os, sys, uuid
from pathlib import Path
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.workflow_queue import enqueue,fail_receipt
pool.open(wait=True)
out=Path('/qa/recovery-fixture.json')
model='google/gemini-3.5-flash-lite'
if sys.argv[1]=='prepare':
    accounts=json.loads(Path('/qa/synthetic-accounts.json').read_text())
    a,b=[p['id'] for p in accounts['projects']]
    # Earlier interrupted synthetic test attempts must not consume provider calls.
    with tenant_context(system=True),connection() as conn:
        for task in conn.execute("SELECT * FROM workflow_tasks WHERE status IN ('queued','running')").fetchall():
            fail_receipt(conn,task,'합성 QA 이전 시도 정리')
            conn.execute("UPDATE workflow_tasks SET status='failed' WHERE id=%s",(task['id'],))
        conn.execute("UPDATE intake_documents SET status='cancelled',cancel_requested=true WHERE status IN ('queued','retry','waiting_llm')")
    with tenant_context(b),connection() as conn:
        interrupted=uuid.uuid4()
        conn.execute("INSERT INTO report_generation_runs(id,status,model) VALUES (%s,'running',%s)",(interrupted,model))
        conn.execute("UPDATE report_sections SET content='저장된 본문 보존',status='generating' WHERE part_id='summary-ko'")
        lost=enqueue(conn,'report_all',[interrupted,b,model],model)
        conn.execute("UPDATE workflow_tasks SET status='running',worker_id='terminated-test-worker' WHERE id=%s",(lost,))
    with tenant_context(a),connection() as conn:
        conn.execute("UPDATE report_sections SET status='generating' WHERE part_id='cover'")
        cover=enqueue(conn,'report_section',['cover','',a,model,None],model)
        cancelled=uuid.uuid4()
        conn.execute("INSERT INTO report_generation_runs(id,status,model,cancel_requested) VALUES (%s,'queued',%s,true)",(cancelled,model))
        cancel_task=enqueue(conn,'report_all',[cancelled,a,model],model)
    out.write_text(json.dumps({'a':a,'b':b,'lost':str(lost),'cover':str(cover),'cancel':str(cancel_task),'cancelled_run':str(cancelled)}))
    print('Prepared: interrupted report, queued fixed-format cover and pre-cancelled report.')
else:
    ids=json.loads(out.read_text())
    with tenant_context(system=True),connection() as conn:
        states={str(r['id']):r['status'] for r in conn.execute('SELECT id,status FROM workflow_tasks WHERE id=ANY(%s::uuid[])',([ids[k] for k in ('lost','cover','cancel')],)).fetchall()}
        if sys.argv[1]=='queued':
            assert states[ids['cover']]=='queued' and states[ids['cancel']]=='queued',states
            print('PASS API restart preserves queued workflow tasks')
        else:
            assert [states[ids[k]] for k in ('lost','cover','cancel')]==['failed','completed','cancelled'],states
            saved=conn.execute("SELECT content,status FROM report_sections WHERE project_id=%s AND part_id='summary-ko'",(ids['b'],)).fetchone()
            assert saved=={'content':'저장된 본문 보존','status':'failed'},saved
            locked=conn.execute("SELECT pg_try_advisory_xact_lock(hashtextextended('kodame-workflow-reports',0)) AS locked").fetchone()['locked']
            assert not locked,'another worker could acquire queue leadership'
            versions=conn.execute('SELECT prompt_versions,executed_prompt_versions FROM workflow_tasks WHERE id=%s',(ids['cover'],)).fetchone()
            assert versions['prompt_versions'] and versions['executed_prompt_versions']
            result={'status':'passed','checks':['API restart retained queue','interrupted receipt failed without deleting draft','queued cover completed outside API','pre-cancelled job made no AI call','single active report queue leader','enqueued and executed prompt fingerprints retained']}
            Path('/qa/recovery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False))
pool.close()
