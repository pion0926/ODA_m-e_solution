"""Opt-in paid AI probe using ONLY synthetic QA documents.

No production documents, sessions, or settings are used. Requires the QA database
and an explicitly supplied provider key. Invocation supports bounded stages.
"""
import json,os,sys,time,uuid
from pathlib import Path
from psycopg.types.json import Jsonb
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
assert os.getenv('OPENROUTER_API_KEY')
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.llm_models import llm_model_context
from kodame_intake.workflow_queue import dispatch,enqueue,finish_task
pool.open(wait=True)
info=json.loads(Path('/qa/synthetic-accounts.json').read_text())
project=info['projects'][0]['id']; stage=sys.argv[1]; start=time.monotonic()
with tenant_context(project),connection() as conn:
    row=conn.execute('SELECT id,name,llm_model FROM projects WHERE id=%s',(project,)).fetchone()
    assert row['name'].startswith('합성 QA ')
    actor=conn.execute('SELECT account_id FROM project_members WHERE project_id=%s LIMIT 1',(project,)).fetchone()['account_id']
model=row['llm_model']
with tenant_context(project,account_id=actor),llm_model_context(model):
    if stage=='foundation':
        from kodame_intake.ai_gateway import analyze_document
        from kodame_intake.project_overview import generate_project_overview
        with connection() as conn:
            document=conn.execute("SELECT * FROM active_intake_documents WHERE upload_role='project_plan' AND status='completed'").fetchone()
        analysis=analyze_document(document['original_name'],Path(document['extracted_path']).read_text(),upload_role='project_plan')
        from kodame_intake.foundation_facts import extract_plan_facts
        analysis['overview_facts']=extract_plan_facts(Path(document['extracted_path']).read_text())
        with connection() as conn:
            conn.execute('UPDATE intake_documents SET summary=%s,analysis=%s,updated_at=now() WHERE id=%s',
                         (analysis['summary'],Jsonb(analysis),document['id']))
        overview_id=generate_project_overview()
        with connection() as conn:
            result=conn.execute('SELECT overview FROM project_overviews WHERE id=%s',(overview_id,)).fetchone()
        assert result['overview']['project_name']['text']!='확인 필요', 'Synthetic plan has an explicit project name'
        result['status']='completed'
    elif stage=='facts':
        from kodame_intake.evidence_matching import match_foundations
        with connection() as conn:
            document=conn.execute("SELECT * FROM intake_documents WHERE original_name='실적현황_QA.txt'").fetchone()
        result=match_foundations(Path(document['extracted_path']).read_text())
        facts=(result.get('registration_facts') or {}).get('facts',[])
        assert facts and result['pdm'], 'Synthetic document should yield facts and PDM matches'
        result={'status':'passed','pdm_matches':len(result['pdm']),'facts':len(facts),
                'summary':result['registration_facts'].get('summary'),'facts_detail':facts}
    elif stage=='dac':
        from kodame_intake.dac_review import build_plan,validate_selection
        from kodame_intake.evaluation_runner import run_all
        plan=build_plan()
        # Use all synthetic source documents for this controlled, tiny project.
        ids=[d['id'] for d in plan['documents'] if d['status']=='completed']
        mappings={q['id']:ids for q in plan['indicators']}
        reviewed=validate_selection(plan,plan['revision'],mappings,list(mappings))
        run=uuid.uuid4()
        with connection() as conn:
            conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count,input_snapshot) VALUES (%s,'queued',%s,%s,%s)",
                         (run,model,len(ids),Jsonb({'review_plan':reviewed})))
        run_all(run,project,model)
        with connection() as conn:
            result=conn.execute('SELECT status,error_message FROM evaluation_runs WHERE id=%s',(run,)).fetchone()
            result['scores']=conn.execute('SELECT criterion_id,score FROM criterion_evaluations WHERE run_id=%s',(run,)).fetchall()
    elif stage in ('report','resume'):
        from kodame_intake.report_generator import generate_all_report_sections
        from kodame_intake.project_lifecycle import capture_input_snapshot
        run=uuid.uuid4()
        with connection() as conn:
            snapshot=capture_input_snapshot(conn)
            preserved=[]
            if stage=='resume':
                from kodame_intake.report_resume import resumable_parts
                previous=conn.execute('SELECT * FROM report_generation_runs ORDER BY started_at DESC LIMIT 1').fetchone()
                sections=conn.execute('SELECT * FROM report_sections').fetchall()
                preserved=resumable_parts(previous,sections,snapshot)
                assert preserved, 'Resume must preserve successful sections'
            conn.execute("INSERT INTO report_generation_runs(id,model,input_snapshot,resume_part_ids) VALUES (%s,%s,%s,%s)",(run,model,Jsonb(snapshot),Jsonb(preserved)))
        generate_all_report_sections(run,project,model)
        with connection() as conn:
            result=conn.execute('SELECT status,completed_sections,failed_sections,error_message FROM report_generation_runs WHERE id=%s',(run,)).fetchone()
            result['sections']=conn.execute('SELECT part_id,status,error_message,quality_score FROM report_sections ORDER BY section_number').fetchall()
            result['preserved_sections']=len(preserved)
    elif stage=='export':
        from kodame_intake.report_exporter import run_report_export
        from kodame_intake.report_generator import report_export_readiness
        from kodame_intake.project_lifecycle import project_lifecycle
        readiness=report_export_readiness(project)
        assert readiness['ready'], readiness['issues']
        assert project_lifecycle()['report_current'], 'Report must match current inputs'
        run=uuid.uuid4()
        with connection() as conn:
            conn.execute("INSERT INTO report_exports(id) VALUES (%s)",(run,))
        run_report_export(run,project)
        with connection() as conn:
            result=conn.execute('SELECT status,error_message,output_path,validation FROM report_exports WHERE id=%s',(run,)).fetchone()
        if result['status']=='completed':
            import shutil
            shutil.copyfile(result['output_path'],'/qa/synthetic-final-report.hwpx')
    else:
        raise ValueError('Unknown stage')
result.update(stage=stage,project_id=project,model=model,elapsed_seconds=round(time.monotonic()-start,1))
Path('/qa/live-'+stage+'.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
summary={key:value for key,value in result.items() if key not in ('validation','sections','overview','facts_detail')}
if stage=='export':
    validation=result.get('validation') or {}
    summary.update(pages=validation.get('rhwp_page_count'),toc_verified=validation.get('rhwp_toc_verified'),
                   layout_ok=(validation.get('layout_contract') or {}).get('ok'))
print(json.dumps(summary,ensure_ascii=False,default=str),flush=True)
pool.close()
if result.get('status') not in ('passed','completed'):
    raise RuntimeError(f"Synthetic {stage} did not complete successfully: {result.get('status')}")
