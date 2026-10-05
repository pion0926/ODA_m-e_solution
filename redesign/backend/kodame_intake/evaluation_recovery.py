"""Run-local durable checkpoints, copied only for identical tenant inputs."""
import uuid
from psycopg.types.json import Jsonb
from .db import connection
from .evaluation_storage import retry_storage

RECOVERY_VERSION = 'dac-recovery-v1'


def restore_run(run_id, digest, snapshot):
    with connection() as conn, conn.transaction():
        previous = conn.execute("""SELECT * FROM evaluation_runs
            WHERE status='failed' AND id<>%s AND input_snapshot->>'recovery_version'=%s
            AND input_snapshot->>'resume_fingerprint'=%s
            AND input_snapshot->>'document_digest'=%s ORDER BY started_at DESC LIMIT 1""",
            (run_id, RECOVERY_VERSION, digest, snapshot['document_digest'])).fetchone()
        if not previous:
            return None
        data = previous['input_snapshot']
        if not data.get('pdm_context') or not data.get('assessment'):
            return None
        overview = conn.execute('SELECT * FROM project_overviews WHERE run_id=%s ORDER BY created_at DESC LIMIT 1',
                                (previous['id'],)).fetchone()
        if not overview:
            return None
        conn.execute('''INSERT INTO project_overviews
            (id,run_id,model,document_count,overview,source_document_ids,conflicts)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (uuid.uuid4(),run_id,overview['model'],overview['document_count'],Jsonb(overview['overview']),
             Jsonb(overview['source_document_ids']),Jsonb(overview['conflicts'])))
        saved = {**data, **snapshot, 'resumed_from_run_id':str(previous['id'])}
        conn.execute('UPDATE evaluation_runs SET input_snapshot=%s WHERE id=%s', (Jsonb(saved),run_id))
        return saved


@retry_storage
def save_context(run_id, digest, assessment, pdm):
    with connection() as conn:
        conn.execute('UPDATE evaluation_runs SET input_snapshot=input_snapshot || %s WHERE id=%s',
                     (Jsonb({'recovery_version':RECOVERY_VERSION,'resume_fingerprint':digest,
                             'assessment':assessment,'pdm_context':pdm,'question_checkpoints':{}}),run_id))


@retry_storage
def save_question(run_id, qid, digest, raw):
    with connection() as conn:
        conn.execute("""UPDATE evaluation_runs SET input_snapshot=jsonb_set(input_snapshot,
            ARRAY['question_checkpoints',%s],%s) WHERE id=%s AND status='running'""",
            (qid, Jsonb({'digest':digest,'raw':raw}),run_id))


@retry_storage
def save_selection(run_id, digest, raw):
    with connection() as conn:
        conn.execute("""UPDATE evaluation_runs SET input_snapshot=jsonb_set(input_snapshot,
            '{evidence_selections}',coalesce(input_snapshot->'evidence_selections','{}'::jsonb) || %s)
            WHERE id=%s AND status='running'""", (Jsonb({digest:raw}),run_id))


@retry_storage
def set_current_question(run_id, qid):
    with connection() as conn:
        conn.execute("UPDATE evaluation_runs SET input_snapshot=input_snapshot || %s WHERE id=%s",
                     (Jsonb({'current_question':qid}),run_id))


@retry_storage
def set_stage(run_id, stage, **details):
    with connection() as conn:
        conn.execute('UPDATE evaluation_runs SET input_snapshot=input_snapshot || %s WHERE id=%s',
                     (Jsonb({'current_stage':stage,**details}),run_id))
