"""Resumable, two-phase evidence-purpose upgrade. Never edits evaluation results.

Run prepare with the configured project provider; inspect the aggregate summary,
then apply only when each project's inputs and mapping overrides are unchanged.
Candidate files contain private document facts: keep them on the service volume.
"""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from psycopg.types.json import Jsonb
from .db import pool, connection, tenant_context
from .evidence_matching import foundation_context, match_foundations, save_pdm_assignments
from .pdm_mapping_policy import VERSION, manual_overrides, decision
from .llm_models import llm_model_context
from .project_ai import get_project_model
from .project_lifecycle import lock_project_workflow, active_workflow_jobs


def stamp(row):
    return hashlib.sha256(json.dumps([str(row['id']), row['sha256'], row['analysis']],sort_keys=True,default=str).encode()).hexdigest()


def prepare_project(project_id, root):
    with tenant_context(project_id):
        context=foundation_context()
        model=get_project_model()
        with connection() as conn:
            docs=conn.execute("SELECT * FROM evaluation_intake_documents WHERE status='completed' AND upload_role='evidence' ORDER BY queue_position").fetchall()
        def one(doc):
            path=root/(str(doc['id'])+'.json')
            if path.exists():
                candidate=json.loads(path.read_text())
                if (candidate['stamp']==stamp(doc) and candidate['sources']==context['sources']
                        and candidate.get('matches', {}).get('version') == VERSION):
                    return candidate
            with tenant_context(project_id), llm_model_context(model):
                text=Path(doc['extracted_path']).read_text(encoding='utf-8')
                artifact=(doc.get('analysis') or {}).get('intake_mode')=='artifact'
                if artifact:
                    from .intake_triage import sample_text
                    text=sample_text(text)
                matches=match_foundations(text,context=context,artifact=artifact)
                candidate={'id':str(doc['id']),'project_id':str(project_id),'stamp':stamp(doc),
                    'sources':context['sources'],'matches':matches,'model':model}
                temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(candidate,ensure_ascii=False),encoding='utf-8'); temp.replace(path)
                return candidate
        results=[];errors=[]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures={executor.submit(one,doc):doc for doc in docs}
            for f in as_completed(futures):
                doc=futures[f]
                try:
                    candidate=f.result(); results.append(candidate)
                    print(json.dumps({'document_id':str(doc['id']),'status':'prepared','matches':len(candidate['matches']['pdm'])}),flush=True)
                except Exception as exc:
                    # No raw provider content or source text in the operational log.
                    errors.append({'document_id':str(doc['id']),'error_type':type(exc).__name__})
        return {'project_id':str(project_id),'documents':len(docs),'prepared':len(results),'errors':errors,
                'before':sum(len((d.get('analysis') or {}).get('evidence_matches',{}).get('pdm',[])) for d in docs),
                'after':sum(len(r['matches']['pdm']) for r in results)}


def apply_project(project_id, root):
    with tenant_context(project_id), connection() as conn:
        lock_project_workflow(conn)
        if active_workflow_jobs(conn):
            raise RuntimeError('Active workflow: retry after completion')
        docs=conn.execute("SELECT * FROM evaluation_intake_documents WHERE status='completed' AND upload_role='evidence' ORDER BY queue_position FOR UPDATE").fetchall()
        context=foundation_context()
        candidates=[]
        for doc in docs:
            value=json.loads((root/(str(doc['id'])+'.json')).read_text())
            if (value['stamp']!=stamp(doc) or value['sources']!=context['sources']
                    or value.get('matches', {}).get('version') != VERSION):
                raise RuntimeError('Inputs changed; prepare again before applying')
            candidates.append(value)
        for doc,candidate in zip(docs,candidates):
            a=dict(doc.get('analysis') or {})
            included,excluded=manual_overrides(a,context['sources']['pdm']['id'])
            a.setdefault('mapping_history',[]).append({'version':(a.get('evidence_matches') or {}).get('version'),
                'evidence_matches':a.get('evidence_matches'),'overrides':a.get('pdm_mapping_overrides')})
            a['pdm_mapping_overrides']={'version':VERSION,'source_document_id':context['sources']['pdm']['id'],
                                       'included':sorted(included),'excluded':sorted(excluded)}
            # Preserve separately registered DAC/report links and old measurement caches.
            a['evidence_matches']={**(a.get('evidence_matches') or {}),**candidate['matches']}
            a['registration_facts']=candidate['matches']['registration_facts']
            summary=a['registration_facts'].get('summary') or doc.get('summary','')
            a['summary']=summary
            conn.execute('UPDATE intake_documents SET analysis=%s,summary=%s,updated_at=now() WHERE id=%s',(Jsonb(a),summary,doc['id']))
            effective=[]
            for i in context['indicators']:
                match=decision({'analysis':a},i['id'],context['sources']['pdm']['id'])
                if match: effective.append({**match,'tier':i['tier'],'requirement_title':i['mov']})
            save_pdm_assignments(conn,doc['id'],{'pdm':effective})
        # Explicit foundation uploads define the business/indicators, not evidence.
        conn.execute("DELETE FROM pdm_document_assignments WHERE document_id IN (SELECT id FROM intake_documents WHERE upload_role IN ('pdm','project_plan'))")
        return {'project_id':str(project_id),'status':'applied','documents':len(docs)}


def review_prepared_scopes(project_id, root):
    """Recheck contradictory reported-result scope candidates without rereading all files."""
    from .pdm_scope_review import review_reference_scopes
    with tenant_context(project_id), llm_model_context(get_project_model(project_id)):
        context = foundation_context()
        with connection() as conn:
            docs = conn.execute("SELECT * FROM evaluation_intake_documents WHERE status='completed' AND upload_role='evidence' ORDER BY queue_position").fetchall()
        reviewed, promoted = 0, 0
        for doc in docs:
            path = root / (str(doc['id']) + '.json')
            candidate = json.loads(path.read_text(encoding='utf-8'))
            if (candidate['stamp'] != stamp(doc) or candidate['sources'] != context['sources']
                    or candidate.get('matches', {}).get('version') != VERSION):
                raise RuntimeError('Inputs changed; prepare again before reviewing scopes')
            previous_count = len(candidate['matches']['pdm'])
            matches, count = review_reference_scopes(candidate['matches'], context)
            if not count:
                continue
            candidate['matches'] = matches
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(candidate, ensure_ascii=False), encoding='utf-8')
            temp.replace(path)
            reviewed += count
            promoted += len(matches['pdm']) - previous_count
        return {'project_id': str(project_id), 'status': 'scope_reviewed',
                'reviewed_candidates': reviewed, 'new_direct_pairs': promoted}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','apply','review-scopes'])
    parser.add_argument('--root',required=True);parser.add_argument('--project')
    args=parser.parse_args();root=Path(args.root);root.mkdir(parents=True,exist_ok=True)
    pool.open(wait=True)
    try:
        with tenant_context(system=True),connection() as c:
            projects=c.execute("SELECT project_id FROM active_intake_documents WHERE status='completed' AND upload_role IN ('pdm','project_plan') GROUP BY project_id HAVING count(DISTINCT upload_role)=2").fetchall()
        for p in projects:
            if args.project and str(p['project_id'])!=args.project:continue
            handler = {'prepare': prepare_project, 'apply': apply_project, 'review-scopes': review_prepared_scopes}[args.mode]
            result=handler(p['project_id'],root)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if result.get('errors'):raise RuntimeError('Some documents failed: completed candidates retained for retry')
    finally:pool.close()

if __name__=='__main__':main()
