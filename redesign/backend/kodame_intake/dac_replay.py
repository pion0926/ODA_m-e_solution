"""Tenant-scoped, immutable replay of an identical evaluated input set."""
import hashlib
import json
import uuid

from psycopg.types.json import Jsonb

from .assessment_context import assessment_date
from .db import connection
from .dac_rules import RULE_DIGEST, PROMPT_VERSION


def fingerprint(documents, model, review_plan=None):
    with connection() as conn:
        pdm = conn.execute('SELECT model,source_document_id FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
        overview = conn.execute('SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1').fetchone()
    # Never key by counts or mutable timestamps alone; all source content and selection inputs participate.
    document_inputs = [{key:doc.get(key) for key in ('id','sha256','name','summary','document_type','period',
                         'organizations','quality_flags','assigned_criteria')} for doc in documents]
    data = {'version': 'dac-replay-v2-question-scoped',
            'documents':sorted(document_inputs,key=lambda d:d['id']), 'model':model,
            'rubric':RULE_DIGEST,'prompt':PROMPT_VERSION,'date':assessment_date().isoformat(),
            'pdm':pdm,'overview':overview, 'review_scope':
                {'version':review_plan['version'], 'scopes':review_plan['scopes']} if review_plan else None}
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def replay_if_identical(run_id, digest, snapshot):
    with connection() as conn, conn.transaction():
        old = conn.execute("""SELECT * FROM evaluation_runs WHERE status='completed'
            AND input_snapshot->>'assessment_fingerprint'=%s ORDER BY completed_at DESC LIMIT 1""", (digest,)).fetchone()
        if not old:
            return False
        count = conn.execute('SELECT count(*) AS n FROM criterion_evaluations WHERE run_id=%s',(old['id'],)).fetchone()['n']
        if count != 5:
            return False
        conn.execute('''INSERT INTO criterion_evaluations
            (run_id,criterion_id,criterion_name,score,summary,score_reason,question_assessments,evidence_document_ids,evidence_gaps,source_document_count)
            SELECT %s,criterion_id,criterion_name,score,summary,score_reason,question_assessments,evidence_document_ids,evidence_gaps,source_document_count
            FROM criterion_evaluations WHERE run_id=%s ORDER BY id''',(run_id,old['id']))
        conn.execute('''INSERT INTO project_overviews (id,run_id,model,document_count,overview,source_document_ids,conflicts)
            SELECT %s,%s,model,document_count,overview,source_document_ids,conflicts FROM project_overviews
            WHERE run_id=%s ORDER BY created_at DESC LIMIT 1''',(uuid.uuid4(),run_id,old['id']))
        old_snapshot = old['input_snapshot'] or {}
        from .evaluation_versions import whole_run_replay_basis
        replay_basis = whole_run_replay_basis(conn, old, run_id, digest, snapshot)
        saved = {**snapshot,'assessment_fingerprint':digest, 'rubric_digest':RULE_DIGEST,
                 'reused_from_run_id':str(old['id']), 'pdm_context':old_snapshot.get('pdm_context',{}),
                 'assessment':old_snapshot.get('assessment',{}),
                 'question_checkpoints':old_snapshot.get('question_checkpoints',{}),
                 'question_reuse': {qid: {'reused': True, 'source_run_id': str(old['id'])}
                                    for qid in old_snapshot.get('question_checkpoints', {})},
                 'evidence_selections':old_snapshot.get('evidence_selections',{})}
        if replay_basis:
            saved['replay_basis'] = replay_basis
        conn.execute("UPDATE evaluation_runs SET status='completed',completed_at=now(),input_snapshot=%s WHERE id=%s",
                     (Jsonb(saved),run_id))
    return True
