"""Dedicated persistent workflow worker. Run once for analysis and once for reports."""
import logging
import os
import signal
import threading
import time
import uuid
from pathlib import Path
from psycopg.types.json import Jsonb
from .db import connection, pool, tenant_context
from .ai.prompt_registry import prompt_manifest
from .workflow_queue import dispatch, fail_receipt, finish_task, receipt

log = logging.getLogger('kodame.workflow')
stop = threading.Event()
HEARTBEAT = Path('/tmp/kodame-workflow-heartbeat')


def heartbeat(leader, guard):
    while not stop.wait(5):
        try:
            with guard:
                leader.execute('SELECT 1')
                leader.commit()
            HEARTBEAT.touch()
        except Exception:
            # Stop this process before it can keep dispatching after losing its
            # leadership session. The next worker surfaces interrupted receipts.
            log.exception('workflow_leadership_connection_lost')
            os._exit(1)


def serve():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    queue = os.getenv('WORKFLOW_QUEUE','analysis')
    slot = max(0, min(7, int(os.getenv('WORKFLOW_SLOT', '0'))))
    leadership_key = 'kodame-workflow-'+queue + (f'-{slot}' if slot else '')
    if queue not in ('analysis','reports'):
        raise ValueError('WORKFLOW_QUEUE must be analysis or reports')
    pool.open(wait=True)
    worker = str(uuid.uuid4())
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    HEARTBEAT.touch()
    guard = threading.Lock()
    try:
        with tenant_context(system=True), connection() as leader:
            acquired = False
            try:
                while not stop.is_set():
                    acquired = leader.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS locked",(leadership_key,)).fetchone()['locked']
                    leader.commit()
                    if acquired:
                        break
                    HEARTBEAT.touch()
                    stop.wait(5)
                if not acquired:
                    return
                threading.Thread(target=heartbeat,args=(leader,guard),daemon=True).start()
                # A previous worker lost its DB session. Preserve successful sections
                # and cached evidence; expose interrupted receipts for explicit resume.
                with connection() as conn:
                    stale = conn.execute("SELECT * FROM workflow_tasks WHERE queue=%s AND worker_slot=%s AND status='running' FOR UPDATE",(queue,slot)).fetchall()
                    for task in stale:
                        message='분석 워커가 중단되었습니다. 저장된 결과는 보존됩니다. 작업을 다시 실행해 주세요.'
                        fail_receipt(conn,task,message)
                        conn.execute("UPDATE workflow_tasks SET status='failed',error_message=%s,completed_at=now() WHERE id=%s",(message,task['id']))
                while not stop.is_set():
                    # Check lock-owning DB session before dispatching another task.
                    with guard:
                        leader.execute('SELECT 1'); leader.commit()
                    with connection() as conn:
                        # Serialize only claims across slots. A project gets at
                        # most one workflow; longest-unserved projects go first.
                        from .workflow_queue import claim_task
                        task = claim_task(conn, worker, slot, queue)
                    if not task:
                        stop.wait(2); continue
                    with connection() as conn:
                        state = receipt(conn, task)
                        if not state or state['status'] not in ('queued','running','generating'):
                            finish_task(conn, task)
                            continue
                    log.info('workflow_start id=%s kind=%s project=%s',task['id'],task['kind'],task['project_id'])
                    try:
                        dispatch(task)
                    except Exception as exc:
                        log.error('workflow_failed id=%s kind=%s error_type=%s',task['id'],task['kind'],type(exc).__name__)
                        message='작업 실행 중 오류가 발생했습니다. 저장된 결과를 확인한 뒤 다시 실행해 주세요.'
                        with connection() as conn:
                            fail_receipt(conn,task,message)
                            conn.execute("UPDATE workflow_tasks SET status='failed',error_message=%s,completed_at=now() WHERE id=%s",(message,task['id']))
                    else:
                        with connection() as conn:
                            status = finish_task(conn, task)
                        log.info('workflow_finished id=%s kind=%s status=%s',task['id'],task['kind'],status)
            finally:
                if acquired:
                    stop.set()
                    with guard:
                        leader.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",(leadership_key,)); leader.commit()
    finally:
        stop.set(); pool.close()


if __name__ == '__main__':
    serve()
