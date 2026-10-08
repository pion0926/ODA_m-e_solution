"""Durable PDM refresh receipt, committed atomically with the PDM snapshot."""
from psycopg.types.json import Jsonb
from .db import connection
from .pdm_monitoring import refresh_pdm_model


def serialize(row):
    if not row:
        return {'status':'not_run', 'active':False}
    return {'id':str(row['id']), 'status':row['status'], 'active':row['status'] in ('queued','running'),
            'snapshot_id':str(row['snapshot_id']) if row.get('snapshot_id') else None,
            'result':row['result'], 'error_message':row.get('error_message'),
            'started_at':row['started_at'].isoformat(),
            'completed_at':row['completed_at'].isoformat() if row.get('completed_at') else None}


def finish_refresh(conn, run_id, snapshot_id, model):
    risk = model.get('risk_analysis') or {}
    incomplete = (model.get('monitoring') or {}).get('evidence_analysis', {}).get('incomplete_indicator_count', 0)
    partial = risk.get('status') == 'fallback' or bool(incomplete)
    evidence = (model.get('monitoring') or {}).get('evidence_analysis') or {}
    result = {'risk_status':risk.get('status'), 'indicator_count':len(model.get('performance_indicators',[])),
              'incomplete_indicator_count':incomplete,
              'mapped_document_count':evidence.get('mapped_document_count',0),
              'restored_pair_count':evidence.get('restored_pair_count',0),
              'observation_count':evidence.get('observation_count',0),
              'message':'PDM 저장 완료 · 일부 AI 분석 재시도 필요' if partial else
                  f"성과 분석 저장 완료 · 신규 문서 {evidence.get('mapped_document_count',0)}건 검토 · 측정값 {evidence.get('observation_count',0)}건"}
    if evidence.get('restored_pair_count'):
        result['message'] += f" · 기존 분석 {evidence['restored_pair_count']}개 조합 재사용·연결 복원"
    conn.execute("""UPDATE pdm_refresh_runs SET status=%s,snapshot_id=%s,result=%s,completed_at=now()
                    WHERE id=%s""", ('partial' if partial else 'completed',snapshot_id,Jsonb(result),run_id))


def run_refresh(run_id):
    try:
        with connection() as conn:
            row = conn.execute("UPDATE pdm_refresh_runs SET status='running' WHERE id=%s RETURNING analysis_plan", (run_id,)).fetchone()
        refresh_pdm_model(analyze_risks=True, refresh_run_id=run_id, analysis_plan=row['analysis_plan'])
    except Exception as exc:
        with connection() as conn:
            conn.execute("""UPDATE pdm_refresh_runs SET status='failed',error_message=%s,completed_at=now()
                            WHERE id=%s AND status IN ('queued','running')""", (str(exc)[:2000],run_id))
        print(f'PDM_REFRESH_FAILED {run_id}: {type(exc).__name__}', flush=True)
