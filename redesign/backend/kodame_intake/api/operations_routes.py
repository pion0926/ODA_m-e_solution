"""Administrator diagnostics: queue counts and prompt identity, never payloads."""
from fastapi import APIRouter, Request
from ..admin import require_admin
from ..db import connection, tenant_context
from ..ai.prompt_registry import prompt_manifest

router = APIRouter()


@router.get('/api/v2/admin/runtime')
def runtime_status(request: Request):
    require_admin(request.state.auth)
    with tenant_context(system=True), connection() as conn:
        tasks = conn.execute("""SELECT queue,status,count(*) AS count,
            coalesce(max(extract(epoch FROM now()-created_at)) FILTER (WHERE status='queued'),0) AS oldest_wait_seconds
            FROM workflow_tasks WHERE created_at>now()-interval '7 days' OR status IN ('queued','running')
            GROUP BY queue,status ORDER BY queue,status""").fetchall()
        intake = conn.execute("SELECT status,count(*) AS count FROM active_intake_documents GROUP BY status ORDER BY status").fetchall()
        usage = conn.execute('''SELECT count(*) AS requests,coalesce(sum(tokens),0) AS tokens,
            coalesce(sum(cost_usd),0) AS cost_reserved_or_confirmed_usd,
            count(*) FILTER(WHERE usage_confirmed) AS usage_confirmed_requests
            FROM ai_request_reservations WHERE created_at>now()-interval '24 hours' ''').fetchone()
        migrations = conn.execute('SELECT version,applied_at FROM schema_migrations ORDER BY version').fetchall()
    return {'service_version':'2.4','workflows':tasks,'intake':intake, 'ai_last_24h':usage, 'migrations':migrations,
            'prompt_versions':prompt_manifest(),
            'worker_health':'Use Compose health status; queue age alone does not prove worker liveness.'}
