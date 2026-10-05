"""Explicit project foundations, with analysis-success promotion and retained history."""
from fastapi import HTTPException

from .db import connection
from .project_lifecycle import active_workflow_jobs, lock_project_workflow

ROLES = ('project_plan', 'pdm')


def replacement_impact(conn, role):
    from .evaluation_versions import digest
    if role not in ROLES:
        raise HTTPException(422, '기준 문서 종류를 확인해 주세요.')
    current = state(conn)['documents'].get(role)
    model = conn.execute('SELECT model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    mappings = conn.execute('SELECT document_id,indicator_id FROM pdm_document_assignments ORDER BY document_id,indicator_id').fetchall()
    result = {'role': role, 'current_document': current,
              'indicators': [i for t in (model or {}).get('model', {}).get('tiers', []) for i in t['indicators']],
              'mappings': [{**m, 'document_id': str(m['document_id'])} for m in mappings],
              'report_sections': conn.execute("SELECT part_id FROM report_sections WHERE content<>'' ORDER BY section_number").fetchall(),
              'policy': '원본·기존 평가 버전은 보존됩니다. 새 기준 문서 분석 성공 후 사업개요/PDM을 갱신하며 평가·보고서는 재검토 대상이 됩니다.'}
    return {**result, 'revision': digest(result)}

# One-time adoption only uses already analysed roles; it never reclassifies files.
MIGRATION = """
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='intake_documents' AND column_name='upload_role') THEN
  ALTER TABLE intake_documents ADD COLUMN upload_role text NOT NULL DEFAULT 'evidence'
    CHECK (upload_role IN ('evidence','project_plan','pdm'));
  ALTER TABLE intake_documents ADD COLUMN superseded_at timestamptz;
  UPDATE intake_documents SET upload_role='pdm' WHERE id IN (
    SELECT DISTINCT ON (project_id) id FROM intake_documents
    WHERE status='completed' AND analysis->'content_classification'->>'is_pdm_source'='true'
    ORDER BY project_id,queue_position DESC);
  UPDATE intake_documents SET upload_role='project_plan' WHERE id IN (
    SELECT DISTINCT ON (project_id) id FROM intake_documents
    WHERE status='completed' AND upload_role='evidence'
      AND analysis->'content_classification'->>'is_project_plan'='true'
    ORDER BY project_id,queue_position DESC);
  UPDATE intake_documents SET analysis=COALESCE(analysis,'{}'::jsonb)
    || jsonb_build_object('upload_role',upload_role);
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS intake_documents_active_dedupe_idx
 ON intake_documents(project_id,original_name,sha256,upload_role) WHERE superseded_at IS NULL;
CREATE OR REPLACE VIEW active_intake_documents WITH (security_invoker=true) AS
 SELECT * FROM intake_documents WHERE superseded_at IS NULL;
"""


def state(conn=None):
    if conn is None:
        with connection() as current:
            return state(current)
    rows = conn.execute("""SELECT DISTINCT ON (upload_role)
        id,original_name,upload_role,status,progress,error_message
        FROM active_intake_documents WHERE upload_role IN ('project_plan','pdm')
        ORDER BY upload_role,queue_position DESC""").fetchall()
    documents = {row['upload_role']: {**row, 'id': str(row['id'])} for row in rows}
    return {'documents': documents,
            'ready': all(documents.get(role, {}).get('status') == 'completed' for role in ROLES)}


def validate_upload(conn, role, replaces):
    lock_project_workflow(conn)
    current = state(conn)
    if role == 'evidence':
        if not current['ready']:
            raise HTTPException(409, '사업계획서와 PDM을 먼저 업로드하고 두 문서의 분석 완료를 기다려 주세요.')
        return
    if active_workflow_jobs(conn):
        raise HTTPException(409, '평가·보고서·지표 작업이 완료된 뒤 기준 문서를 교체해 주세요.')
    if conn.execute("SELECT id FROM active_intake_documents WHERE status IN ('queued','retry','processing','waiting_llm') AND upload_role=%s LIMIT 1", (role,)).fetchone():
        raise HTTPException(409, '이 기준 문서를 분석 중입니다. 완료 후 교체해 주세요.')
    previous = current['documents'].get(role)
    if previous and replaces != previous['id']:
        raise HTTPException(409, '기준 문서가 변경되었거나 교체 확인이 필요합니다. 새로고침 후 전체 사업 구성 변경을 확인해 주세요.')
    if not previous and replaces:
        raise HTTPException(409, '기준 문서 상태가 변경되었습니다. 새로고침해 주세요.')


def promote(conn, document_id, role):
    """Called in the transaction that marks the successfully analysed file complete."""
    if role not in ROLES:
        return
    lock_project_workflow(conn)
    old = conn.execute("""UPDATE intake_documents SET superseded_at=now(),updated_at=now()
        WHERE upload_role=%s AND id<>%s AND superseded_at IS NULL RETURNING id""",
        (role, document_id)).fetchall()
    for row in old:
        from psycopg.types.json import Jsonb
        archived = {table: conn.execute(f'SELECT * FROM {table} WHERE document_id=%s', (row['id'],)).fetchall()
                    for table in ('slot_suggestions', 'document_slot_assignments', 'pdm_document_assignments')}
        from .evaluation_versions import canonical
        conn.execute('UPDATE foundation_changes SET impact=impact || %s WHERE document_id=%s',
                     (Jsonb({'archived_mappings': canonical(archived)}), document_id))
        conn.execute('DELETE FROM slot_suggestions WHERE document_id=%s', (row['id'],))
        conn.execute('DELETE FROM document_slot_assignments WHERE document_id=%s', (row['id'],))
        conn.execute('DELETE FROM pdm_document_assignments WHERE document_id=%s', (row['id'],))
