"""Aggregate-only inventory. No document text, account credentials or writes."""
import json,os
import psycopg
from psycopg.rows import dict_row
with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row) as conn:
    conn.execute('SET TRANSACTION READ ONLY')
    conn.execute("SELECT set_config('kodame.system_access','on',true)")
    projects=conn.execute("""SELECT p.id,p.name,p.llm_model,
        (SELECT count(*) FROM project_members m WHERE m.project_id=p.id) AS members,
        (SELECT count(*) FROM intake_documents d WHERE d.project_id=p.id AND d.superseded_at IS NULL) AS documents,
        (SELECT count(*) FROM intake_documents d WHERE d.project_id=p.id AND d.superseded_at IS NULL AND d.status='completed') AS completed_documents,
        (SELECT count(*) FROM report_sections s WHERE s.project_id=p.id AND length(trim(s.content))>0) AS written_sections,
        (SELECT count(*) FROM report_sections s WHERE s.project_id=p.id AND s.status='generating') AS generating_sections,
        (SELECT count(*) FROM pdm_document_assignments a WHERE a.project_id=p.id) AS pdm_links,
        (SELECT jsonb_agg(jsonb_build_object('role',upload_role,'status',status,'n',n)) FROM
          (SELECT upload_role,status,count(*) AS n FROM intake_documents d WHERE d.project_id=p.id AND superseded_at IS NULL GROUP BY upload_role,status) q) AS document_states
        FROM projects p WHERE NOT p.is_bootstrap ORDER BY p.created_at""").fetchall()
    work={}
    for table in ('evaluation_runs','pdm_refresh_runs','report_generation_runs','report_exports','presentation_exports'):
        work[table]=conn.execute(f'SELECT status,count(*) AS n FROM {table} GROUP BY status').fetchall()
    print(json.dumps({'projects':projects,'workflows':work},ensure_ascii=False,default=str))
