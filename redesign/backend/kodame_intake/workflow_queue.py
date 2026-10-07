"""Transactional outbox for long-running project workflows.

Enqueue in the same transaction as the public job receipt. API processes never
execute workflows. One advisory lock elects an active worker for each queue.
"""
import uuid
from psycopg.types.json import Jsonb
from .db import current_project_id, current_account_id

MIGRATION = """
CREATE TABLE IF NOT EXISTS workflow_tasks (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 account_id uuid REFERENCES accounts(id) ON DELETE SET NULL,
 kind text NOT NULL, queue text NOT NULL, arguments jsonb NOT NULL, model text NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed','cancelled','partial')),
 created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz,
 error_message text, worker_id text
);
CREATE INDEX IF NOT EXISTS workflow_tasks_pending ON workflow_tasks(queue,created_at) WHERE status='queued';
CREATE INDEX IF NOT EXISTS workflow_tasks_project ON workflow_tasks(project_id,created_at);
ALTER TABLE workflow_tasks ADD COLUMN IF NOT EXISTS prompt_versions jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE workflow_tasks ADD COLUMN IF NOT EXISTS executed_prompt_versions jsonb;
"""

QUEUES = {'pdm':'analysis','dac':'analysis','report_section':'reports','report_all':'reports',
          'report_export':'reports','presentation':'reports','translation':'analysis'}
RECEIPTS = {'pdm':'pdm_refresh_runs','dac':'evaluation_runs','report_all':'report_generation_runs',
            'report_export':'report_exports','presentation':'presentation_exports','translation':'translation_jobs'}


def receipt(conn, task):
    if task['kind'] == 'report_section':
        return conn.execute('SELECT status,error_message FROM report_sections WHERE project_id=%s AND part_id=%s',
                            (task['project_id'], task['arguments'][0])).fetchone()
    table = RECEIPTS[task['kind']]
    return conn.execute(f'SELECT status,error_message FROM {table} WHERE project_id=%s AND id=%s',
                        (task['project_id'], task['arguments'][0])).fetchone()


def finish_task(conn, task):
    """Handlers may record failures without raising. Reflect their actual result."""
    result = receipt(conn, task)
    state = result['status'] if result else 'cancelled'
    status = {'generated':'completed','draft':'completed','completed':'completed',
              'partial':'partial','completed_with_errors':'partial','cancelled':'cancelled'}.get(state, 'failed')
    message = result.get('error_message') if result else '연결된 작업이 삭제되었습니다.'
    if state in ('queued','running','generating'):
        message = '작업이 결과를 저장하지 않고 종료되었습니다. 다시 실행해 주세요.'
        fail_receipt(conn,task,message)
    conn.execute('UPDATE workflow_tasks SET status=%s,error_message=%s,completed_at=now() WHERE id=%s',
                 (status,message,task['id']))
    return status


def enqueue(conn, kind, arguments, model):
    from .ai.prompt_registry import prompt_manifest
    if kind not in QUEUES:
        raise ValueError('Unknown workflow kind')
    ident = uuid.uuid4()
    conn.execute('''INSERT INTO workflow_tasks(id,project_id,account_id,kind,queue,arguments,model,prompt_versions)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
        (ident,current_project_id(),current_account_id(),kind,QUEUES[kind],Jsonb([str(v) if isinstance(v,uuid.UUID) else v for v in arguments]),model,Jsonb(prompt_manifest())))
    return ident


def claim_task(conn, worker, slot, queue):
    from .ai.prompt_registry import prompt_manifest
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('workflow-claim',0))")
    task = conn.execute("""UPDATE workflow_tasks SET status='running',started_at=now(),worker_id=%s,worker_slot=%s,executed_prompt_versions=%s
        WHERE id=(SELECT q.id FROM workflow_tasks q WHERE q.queue=%s AND q.status='queued'
        AND NOT EXISTS(SELECT 1 FROM workflow_tasks r WHERE r.project_id=q.project_id AND r.status='running')
        ORDER BY (SELECT max(p.started_at) FROM workflow_tasks p WHERE p.project_id=q.project_id) NULLS FIRST,
                 q.created_at FOR UPDATE OF q SKIP LOCKED LIMIT 1) RETURNING *""", (worker,slot,Jsonb(prompt_manifest()),queue)).fetchone()
    if task is None:
        return None
    from .workflow_models import bind_claimed_model
    try:
        return bind_claimed_model(conn, task)
    except ValueError as exc:
        message = str(exc)
        fail_receipt(conn, task, message)
        conn.execute("UPDATE workflow_tasks SET status='failed',error_message=%s,completed_at=now() WHERE id=%s",
                     (message, task['id']))
        return {**task, 'status': 'failed', 'error_message': message}


def dispatch(task):
    from .db import tenant_context
    from .llm_models import llm_model_context
    from .pdm_jobs import run_refresh
    from .evaluation_runner import run_all
    from .report_generator import generate_all_report_sections, generate_report_section
    from .report_exporter import run_report_export
    from .presentation_reference_export import run_reference_export
    from .translation_jobs import run_translation
    handlers = {'pdm':run_refresh,'dac':run_all,'report_section':generate_report_section,
                'report_all':generate_all_report_sections,'report_export':run_report_export,'presentation':run_reference_export,'translation':run_translation}
    from .ai.job_budget import job_budget
    with tenant_context(task['project_id'],account_id=task['account_id']), llm_model_context(task['model']), job_budget(task['id']):
        handlers[task['kind']](*task['arguments'])


def fail_receipt(conn, task, message):
    # Conditional updates never clobber a result that completed before shutdown.
    kind, ident = task['kind'], task['arguments'][0]
    if kind == 'report_section':
        conn.execute("""UPDATE report_sections SET status='failed',error_message=%s,updated_at=now()
            WHERE project_id=%s AND part_id=%s AND status='generating'""", (message,task['project_id'],ident))
    else:
        table = RECEIPTS[kind]
        conn.execute(f"""UPDATE {table} SET status='failed',error_message=%s,completed_at=now()
            WHERE project_id=%s AND id=%s AND status IN ('queued','running')""",(message,task['project_id'],ident))
        if kind == 'report_all':
            conn.execute("""UPDATE report_sections SET status='failed',error_message=%s,updated_at=now()
                WHERE project_id=%s AND status='generating'""", (message,task['project_id']))
