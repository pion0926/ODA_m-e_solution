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
