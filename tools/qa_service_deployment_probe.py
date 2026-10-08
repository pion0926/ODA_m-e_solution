"""Read-only deployment readiness; no credentials or document contents in output."""
import json
from kodame_intake.db import pool, connection, tenant_context

pool.open()
with tenant_context(system=True), connection() as conn, conn.transaction():
    conn.execute('SET TRANSACTION READ ONLY')
    active = {}
    for table in ('evaluation_runs','report_generation_runs','report_exports','presentation_exports'):
        active[table] = conn.execute(f"SELECT count(*) AS count FROM {table} WHERE status IN ('queued','running')").fetchone()['count']
    active['report_sections'] = conn.execute("SELECT count(*) AS count FROM report_sections WHERE status='generating'").fetchone()['count']
    active['intake_documents'] = conn.execute("SELECT count(*) AS count FROM intake_documents WHERE status IN ('queued','processing','retry','waiting_llm')").fetchone()['count']
    counts = {table:conn.execute(f'SELECT count(*) AS count FROM {table}').fetchone()['count'] for table in ('accounts','projects','project_members','intake_documents','evaluation_runs','report_sections')}
pool.close()
print(json.dumps({'ready_to_restart':not any(active.values()),'active_jobs':active,'record_counts':counts}))
if any(active.values()): raise SystemExit(2)
