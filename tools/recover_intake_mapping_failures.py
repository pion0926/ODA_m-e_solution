"""One-shot recovery for optional mapping validation failures; dry-run by default.

Never touches cancelled/completed documents or real provider/file errors.
Run only after deploying the non-blocking suggestion policy.
"""
import argparse
import json
from psycopg.types.json import Jsonb
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.intake_triage import resolve_route
from kodame_intake.project_lifecycle import active_workflow_jobs, lock_project_workflow
from kodame_intake.worker import event

PREFIXES = ('매칭 근거가 업로드 문서 원문과 일치하지 않습니다.',
            '사업계획서 인용이 등록된 기준 문서와 일치하지 않습니다.',
            '문서 분류 근거 검증 실패: 분류 근거가 원문과 일치하지 않습니다.')


def recover(apply=False):
    with tenant_context(system=True), connection() as conn:
        projects = conn.execute('SELECT id FROM projects').fetchall()
    result = []
    for project in projects:
        with tenant_context(project['id']), connection() as conn, conn.transaction():
            lock_project_workflow(conn)
            if active_workflow_jobs(conn):
                raise RuntimeError('후속 작업 진행 중에는 복구를 실행하지 않습니다.')
            rows = conn.execute("""SELECT * FROM active_intake_documents WHERE upload_role='evidence'
                AND status IN ('failed','retry','awaiting_review') AND NOT cancel_requested
                ORDER BY queue_position FOR UPDATE""").fetchall()
            for row in rows:
                reason = 'automatic_artifact_route' if row['status']=='awaiting_review' else 'unverified_optional_mapping'
                if row['status'] != 'awaiting_review' and not (row.get('error_message') or '').startswith(PREFIXES):
                    continue
                result.append({'id':str(row['id']),'previous_status':row['status'],'reason':reason})
                if not apply:
                    continue
                triage = resolve_route(row['triage']) if row.get('triage') else None
                conn.execute("""UPDATE intake_documents SET status='queued',stage='queued',
                    progress=CASE WHEN extracted_path IS NULL THEN 0 ELSE 45 END,
                    triage=%s,analysis_model=NULL,attempts=0,worker_id=NULL,lease_until=NULL,run_token=NULL,
                    available_at=now(),error_code=NULL,error_message=NULL,completed_at=NULL,updated_at=now()
                    WHERE id=%s""",(Jsonb(triage) if triage else None,row['id']))
                event(conn,row['id'],'queued','queued','자동 매칭 실패 격리 정책을 적용하여 다시 처리합니다.',
                      {'recovery':'optional-mapping-v2','previous_status':row['status'],'previous_error':row.get('error_message'),'reason':reason})
    return {'applied':apply,'documents':result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    pool.open(wait=True)
    try:
        print(json.dumps(recover(args.apply),ensure_ascii=False))
    finally:
        pool.close()
