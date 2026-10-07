"""Reviewable, immutable bundles of inputs, results, mappings and policies."""
import hashlib
import json
import uuid
from psycopg.types.json import Jsonb
from fastapi import HTTPException
from .db import current_account_id
from .ai.prompt_registry import prompt_manifest
from .ai.prompt_compatibility import compatible_input_manifest
from .dac_rules import RULE_DIGEST
from .report_content_policy import QUALITY_TARGETS

REPLAY_BASIS_VERSION = 'verified-whole-run-replay-v1'
REPLAY_INPUT_KEYS = ('assessment_fingerprint', 'document_digest', 'workflow_digest')


def canonical_evaluation_id(conn, evaluation):
    """Only server-recorded whole-run copies can share a report evaluation basis."""
    ident = str(evaluation['id'])
    snapshot = evaluation.get('input_snapshot') or {}
    proof = snapshot.get('replay_basis') or {}
    if not isinstance(proof, dict) or proof.get('version') != REPLAY_BASIS_VERSION:
        return ident
    if (evaluation.get('status') != 'completed' or not evaluation.get('project_id')
            or proof.get('run_id') != ident or proof.get('project_id') != str(evaluation['project_id'])
            or not snapshot.get('reused_from_run_id') or proof.get('source_run_id') != snapshot['reused_from_run_id']
            or proof.get('source_run_id') == ident or proof.get('model') != evaluation.get('model')):
        return ident
    if any(not snapshot.get(key) or proof.get(key) != snapshot[key] for key in REPLAY_INPUT_KEYS):
        return ident
    try:
        root_id = uuid.UUID(proof.get('canonical_run_id', ''))
    except (ValueError, TypeError, AttributeError):
        return ident
    if str(root_id) == ident:
        return ident
    # Never trust a copied/AI-supplied root ID alone. The original completed run
    # must exist in this project and certify the same source, policy and model.
    root = conn.execute('''SELECT id,project_id,model,
        jsonb_build_object('assessment_fingerprint',input_snapshot->'assessment_fingerprint',
            'document_digest',input_snapshot->'document_digest',
            'workflow_digest',input_snapshot->'workflow_digest') AS input_snapshot FROM evaluation_runs
        WHERE id=%s AND project_id=%s AND status='completed' ''',
        (root_id, evaluation['project_id'])).fetchone()
    if (not root or str(root['id']) != str(root_id)
            or str(root.get('project_id')) != str(evaluation['project_id'])
            or root.get('model') != evaluation.get('model')
            or any((root.get('input_snapshot') or {}).get(key) != proof[key] for key in REPLAY_INPUT_KEYS)):
        return ident
    return str(root_id)


def whole_run_replay_basis(conn, old, run_id, assessment_fingerprint, snapshot):
    """Build provenance only in the exact whole-run copy path, never from AI JSON."""
    original = old.get('input_snapshot') or {}
    inputs = {**snapshot, 'assessment_fingerprint': assessment_fingerprint}
    if (old.get('status') != 'completed' or not old.get('project_id') or not old.get('model')
            or any(not inputs.get(key) or original.get(key) != inputs[key] for key in REPLAY_INPUT_KEYS)):
        return None
    return {'version': REPLAY_BASIS_VERSION, 'run_id': str(run_id),
            'project_id': str(old['project_id']), 'source_run_id': str(old['id']),
            'canonical_run_id': canonical_evaluation_id(conn, old), 'model': old['model'],
            **{key: inputs[key] for key in REPLAY_INPUT_KEYS}}


def canonical(value):
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def digest(value):
    return hashlib.sha256(json.dumps(canonical(value), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def project_inputs(conn):
    # Content rather than insertion IDs/timestamps: regenerating an identical
    # overview does not invalidate the evaluation that generated it.
    overview = conn.execute('SELECT overview,conflicts FROM project_overviews ORDER BY created_at DESC LIMIT 1').fetchone()
    pdm = conn.execute('SELECT model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    return canonical({'overview': overview, 'pdm': pdm,
        'pdm_mappings': conn.execute('SELECT document_id,indicator_id FROM pdm_document_assignments JOIN evaluation_intake_documents d ON d.id=document_id ORDER BY document_id,indicator_id').fetchall(),
        'dac_mappings': conn.execute('SELECT document_id,criterion,slot_id FROM document_slot_assignments JOIN evaluation_intake_documents d ON d.id=document_id ORDER BY document_id,criterion').fetchall(),
        'report_mappings': conn.execute('SELECT document_id,section_id,review_status FROM slot_suggestions JOIN evaluation_intake_documents d ON d.id=document_id ORDER BY document_id,section_id').fetchall(),
        'prompts': compatible_input_manifest(prompt_manifest()), 'rubric': RULE_DIGEST, 'writing_policy': QUALITY_TARGETS})


def current_bundle(conn):
    inputs = project_inputs(conn)
    inputs['documents'] = conn.execute('''SELECT id,sha256,original_name,upload_role,analysis
        FROM evaluation_intake_documents WHERE status='completed' ORDER BY id''').fetchall()
    inputs['project'] = conn.execute("SELECT name,llm_model FROM projects WHERE id=NULLIF(current_setting('kodame.project_id',true),'')::uuid").fetchone()
    run = conn.execute("SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1").fetchone()
    results = conn.execute('SELECT criterion_id,score,question_assessments,evidence_gaps FROM criterion_evaluations WHERE run_id=%s ORDER BY criterion_id', (run['id'],)).fetchall() if run else []
    sections = conn.execute('SELECT part_id,title,content,source_document_ids,quality_score,quality_report,generation_model,generation_metadata FROM report_sections ORDER BY section_number').fetchall()
    bundle = canonical({'inputs': inputs, 'evaluation': run, 'results': results, 'sections': sections})
    return {'revision': digest(bundle), 'payload': bundle}


def has_current_approval(conn):
    # Most workspaces have not approved any version. Avoid rebuilding every
    # document cache and report just to discover that no approval can exist.
    if not conn.execute('SELECT 1 FROM evaluation_versions LIMIT 1').fetchone():
        return False
    # With approvals present, retain the complete source/rule/report revision
    # comparison; a time-based cache would risk showing an obsolete approval.
    return bool(conn.execute('SELECT 1 FROM evaluation_versions WHERE revision=%s',
                             (current_bundle(conn)['revision'],)).fetchone())


def approve(conn, review):
    from .project_lifecycle import lock_project_workflow, active_workflow_jobs, project_lifecycle
    lock_project_workflow(conn)
    current = current_bundle(conn)
    if active_workflow_jobs(conn) or current['revision'] != review.revision:
        raise HTTPException(409, '검토 이후 자료나 보고서가 변경되었습니다. 최신 결과를 다시 검토해 주세요.')
    if not project_lifecycle(conn)['report_current']:
        raise HTTPException(409, '최신 자료로 평가와 보고서 작성을 완료한 뒤 승인할 수 있습니다.')
    if not (review.source_fidelity and review.conclusion_validity) or not review.note.strip():
        raise HTTPException(422, '출처 충실성과 결론 타당성을 각각 확인하고 검토 의견을 기록해 주세요.')
    account = conn.execute('SELECT display_name FROM accounts WHERE id=%s', (current_account_id(),)).fetchone()
    ident = uuid.uuid4()
    row = conn.execute('''INSERT INTO evaluation_versions(id,revision,payload,reviewer_id,reviewer_name,review)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,revision) DO NOTHING RETURNING id''',
        (ident, current['revision'], Jsonb(current['payload']), current_account_id(), account['display_name'],
         Jsonb({'source_fidelity': True, 'conclusion_validity': True, 'note': review.note.strip()}))).fetchone()
    return {'id': str(row['id'] if row else conn.execute('SELECT id FROM evaluation_versions WHERE revision=%s', (current['revision'],)).fetchone()['id']),
            'status': 'approved', 'revision': current['revision']}


def compare(before, after):
    changes = []
    def walk(a, b, path):
        if a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                walk(a.get(key), b.get(key), f'{path}/{key}')
        else:
            changes.append({'path': path, 'before': a, 'after': b})
    walk(before, after, '')
    return changes
