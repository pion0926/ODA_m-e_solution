from __future__ import annotations
import uuid
from pathlib import Path
from psycopg.types.json import Jsonb

from .assessment_context import assessment_scope
from .db import connection, open_pool, tenant_context
from .evaluation_criteria import EVALUATION_CRITERIA
from .llm_models import current_llm_model, llm_model_context
from .project_overview import generate_project_overview
from .project_lifecycle import capture_input_snapshot
from .dac_evidence import prepare_documents
from .dac_review import apply_plan
from .dac_pdm import refresh_context as refresh_pdm_context
from .dac_assessor import assess_criterion
from .dac_replay import fingerprint, replay_if_identical
from .dac_rules import RULE_DIGEST
from .evaluation_recovery import restore_run, save_context, set_stage
from .dac_tables import paired_rows
from .openrouter import redact_for_external_analysis, AnalysisError

def _load_documents() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT d.*,ARRAY(SELECT DISTINCT a.criterion FROM document_slot_assignments a
                               WHERE a.document_id=d.id) AS assigned_criteria
               FROM evaluation_intake_documents d
               WHERE d.status='completed'
               ORDER BY d.queue_position"""
        ).fetchall()
    documents = []
    for index, row in enumerate(rows, 1):
        analysis = row.get("analysis") or {}
        documents.append({
            "ref": f"D{index:03d}",
            "id": str(row["id"]),
            "name": row["original_name"],
            "summary": row.get("summary") or analysis.get("summary") or "",
            "document_type": analysis.get("document_type", ""),
            "period": analysis.get("period", ""),
            "organizations": analysis.get("organizations", []),
            "quality_flags": analysis.get("quality_flags", []),
            "assigned_criteria": sorted(set(row.get("assigned_criteria") or []) | set(analysis.get("dac_criteria") or [])),
            "extracted_path": row.get("extracted_path"),
            "stored_path": row.get("stored_path"),
            "sha256": str(row.get("sha256") or ""),
            "extension": row.get("extension"),
            "dac_fulltext_cache": analysis.get("dac_fulltext"),
            "analysis": analysis,
            "review_all": True,
        })
    return documents


def _corpus(criterion_id: str, documents: list[dict]) -> tuple[list[dict], dict[str, str]]:
    id_by_ref = {}
    corpus = []
    for doc in documents:
        review = doc.get("fulltext_review") or {}
        relevant = criterion_id in review.get('reviewed_criteria',doc["assigned_criteria"]) or doc.get('review_all',False)
        if relevant and review.get("status") != "completed":
            raise AnalysisError(f"DAC 전체 본문 분석이 완료되지 않았습니다: {doc['name']}")
        evidence = []
        for chunk in review.get("chunks", []):
            for item in chunk["evidence"]:
                if item["question_id"].startswith(criterion_id + "-") and item not in evidence:
                    evidence.append(item)
        # Explicit target/actual tables are exhaustively enumerated before the
        # model selects facts. Every candidate must be used or explained.
        if criterion_id == 'effectiveness' and doc.get('question_scopes'):
            for qid, scope in doc.get('review_question_ranges', {}).items():
                if qid not in ('effectiveness-q1','effectiveness-q2'):
                    continue
                text = doc.get('review_source_text','')
                selected_text = '\n'.join(text[s:e] for s,e in scope['ranges'])
                for row in paired_rows(redact_for_external_analysis(selected_text)[0]):
                    evidence.append({**row,'question_id':qid,'kind':'context','table_row_candidate':True})
        if not doc.get('question_scopes') and criterion_id == 'effectiveness' and str(doc.get('extension') or '').lower().lstrip('.') in {'xlsx','xlsm'} and doc.get('extracted_path'):
            full_path=Path(doc['extracted_path']).with_suffix('.dac-fulltext.txt')
            if full_path.exists():
                for row in paired_rows(redact_for_external_analysis(full_path.read_text(encoding='utf-8'))[0]):
                    for qid in ('effectiveness-q1','effectiveness-q2'):
                        evidence.append({**row,'question_id':qid,'kind':'context','table_row_candidate':True})
        if relevant and evidence:
            id_by_ref[doc["ref"]] = doc["id"]
        corpus.append({
            "ref": doc["ref"],
            "document_id": doc['id'], "sha256": doc.get('sha256',''),
            "file_name": doc["name"],
            "relevant_slot_assignment": relevant,
            "document_type": doc["document_type"],
            "period": doc["period"],
            "organizations": doc["organizations"],
            "summary": doc["summary"] if not relevant else "전체 본문 분석 근거를 참조",
            "quality_flags": doc["quality_flags"],
            "fulltext_review": {"status": review.get("status"), "character_count": review.get("character_count", 0),
                                "scope": '사용자가 선택한 질문별 원문 범위만 검토함. 범위 밖 자료의 부재나 미실행을 단정하지 말 것.' if doc.get('question_scopes') else '전체 본문',
                                "chunk_count": len(review.get("chunks", []))},
            "question_evidence": evidence,
        })
    return corpus, id_by_ref


def prepare_review(run_id, documents, review_plan, recovered=None):
    review_documents = apply_plan(documents, review_plan)
    resumed_expansion = (recovered or {}).get('scope_escalation') if review_plan else None
    if resumed_expansion:
        # Restore the exact last scope before touching caches. Running the
        # initial narrower plan first would overwrite completed full reviews.
        from .dac_scope_policy import expand_documents
        set_stage(run_id, 'expanded_evidence')
        review_documents = expand_documents(documents, review_documents, resumed_expansion)
        prepare_documents(review_documents, allow_partial=True)
    else:
        set_stage(run_id,'evidence')
        prepare_documents(review_documents,allow_partial=True)
    if review_plan and not resumed_expansion:
        from .dac_scope_policy import escalation_questions, expand_documents
        expanded = escalation_questions(review_documents,
            [q['id'] for c in EVALUATION_CRITERIA.values() for q in c['questions']])
        if expanded:
            # Persist the selected expansion before requests, including a
            # failure midway through full-text review.
            set_stage(run_id, 'expanded_evidence', scope_escalation=expanded)
            review_documents = expand_documents(documents, review_documents, expanded)
            prepare_documents(review_documents, allow_partial=True)
    return review_documents


def run_all(
    run_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    model: str | None = None,
) -> uuid.UUID:
    with tenant_context(project_id, system=project_id is None), llm_model_context(model):
        return _run_all(run_id)


def _run_all(run_id: uuid.UUID | None = None) -> uuid.UUID:
    open_pool()
    selected_model = current_llm_model()
    input_snapshot = capture_input_snapshot()
    documents = _load_documents()
    review_plan = None
    if run_id:
        with connection() as conn:
            queued = conn.execute('SELECT input_snapshot FROM evaluation_runs WHERE id=%s', (run_id,)).fetchone()
        review_plan = (queued['input_snapshot'] or {}).get('review_plan') if queued else None
    if review_plan:
        input_snapshot['review_plan'] = review_plan
    queued_run_id = run_id
    run_id = run_id or uuid.uuid4()
    with connection() as conn, conn.transaction():
        if queued_run_id:
            conn.execute(
                """UPDATE evaluation_runs
                   SET status='running',model=%s,document_count=%s,started_at=now(),completed_at=NULL,error_message=NULL,input_snapshot=%s
                   WHERE id=%s""",
                (selected_model, len(documents), Jsonb(input_snapshot), run_id),
            )
        else:
            conn.execute(
                "INSERT INTO evaluation_runs(id,status,model,document_count,input_snapshot) VALUES (%s,'running',%s,%s,%s)",
                (run_id, selected_model, len(documents), Jsonb(input_snapshot)),
            )
    try:
        if review_plan and review_plan['input_snapshot']['document_digest'] != input_snapshot['document_digest']:
            raise RuntimeError('평가 접수 이후 자료가 변경되었습니다. 검토 계획을 다시 확인해 주세요.')
        if replay_if_identical(run_id, fingerprint(documents, selected_model, review_plan), input_snapshot):
            print(f'EVALUATION_REUSED {run_id}', flush=True)
            return run_id
        recovered = restore_run(run_id, fingerprint(documents, selected_model, review_plan), input_snapshot)
        if recovered:
            assessment = recovered['assessment']
            pdm_context = recovered['pdm_context']
            checkpoints = recovered.get('question_checkpoints', {})
            print(f'EVALUATION_RESUMED {run_id}', flush=True)
        else:
            set_stage(run_id,'overview')
            print(f"GENERATING PROJECT OVERVIEW with {len(documents)} documents", flush=True)
            generate_project_overview(run_id)
            print("COMPLETED PROJECT OVERVIEW", flush=True)
            with connection() as conn:
                overview_row = conn.execute(
                    "SELECT overview FROM project_overviews WHERE run_id=%s ORDER BY created_at DESC LIMIT 1",
                    (run_id,),
                ).fetchone()
            assessment = assessment_scope(overview_row["overview"] if overview_row else {})
            pdm_context = refresh_pdm_context(documents)
            save_context(run_id, fingerprint(documents, selected_model, review_plan), assessment, pdm_context)
            checkpoints = {}
        review_documents = prepare_review(run_id, documents, review_plan, recovered)
        evaluated_fingerprint = fingerprint(documents, selected_model, review_plan)
        criterion_errors = []
        set_stage(run_id,'questions')
        for criterion_id, criterion in EVALUATION_CRITERIA.items():
            print(f"EVALUATING {criterion_id} with {len(documents)} documents", flush=True)
            try:
                corpus, id_by_ref = _corpus(criterion_id, review_documents)
                result = assess_criterion(criterion_id, criterion, corpus, assessment, pdm_context,
                                          run_id=run_id, checkpoints=checkpoints,
                                          selections=(recovered or {}).get('evidence_selections'))
            except AnalysisError as exc:
                criterion_errors.append(f"{criterion['name']}: {exc}")
                continue
            for question in result["question_assessments"]:
                question["document_review"] = {
                    "method": "reviewed_sections" if review_plan else "fulltext_chunks",
                    "document_count": sum(source["relevant_slot_assignment"] for source in corpus),
                    "chunk_count": sum(source["fulltext_review"]["chunk_count"] for source in corpus if source["relevant_slot_assignment"]),
                }
            result["evidence_document_ids"] = list(dict.fromkeys(
                doc_id for question in result["question_assessments"] for doc_id in question["evidence_document_ids"]
            ))
            with connection() as conn, conn.transaction():
                conn.execute(
                    """INSERT INTO criterion_evaluations
                       (run_id,criterion_id,criterion_name,score,summary,score_reason,
                        question_assessments,evidence_document_ids,evidence_gaps,source_document_count)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (run_id, criterion_id, criterion["name"], result["score"], result["summary"],
                     result["score_reason"], Jsonb(result["question_assessments"]),
                     Jsonb(result["evidence_document_ids"]), Jsonb(result["evidence_gaps"]), len(documents)),
                )
            print(f"COMPLETED {criterion_id} score={result['score']}", flush=True)
        if criterion_errors:
            set_stage(run_id,'needs_retry',stage_errors=criterion_errors)
            raise AnalysisError('일부 질문의 검증이 완료되지 않았습니다. 완료된 질문은 보존됩니다. '+' / '.join(criterion_errors)[:3000])
        set_stage(run_id,'saving')
        if fingerprint(_load_documents(), selected_model, review_plan) != evaluated_fingerprint:
            raise RuntimeError('평가 도중 문서 분류·사업개요 또는 PDM 정보가 변경되었습니다. 최신 자료로 재평가해 주세요.')
        with connection() as conn, conn.transaction():
            current_snapshot = capture_input_snapshot(conn)
            if current_snapshot['document_digest'] != input_snapshot['document_digest']:
                raise RuntimeError('평가 도중 업로드 자료가 변경되었습니다. 최신 자료로 재평가해 주세요.')
            saved = {**input_snapshot, 'workflow_digest': current_snapshot.get('workflow_digest'),
                     'pdm_context':pdm_context, 'assessment_fingerprint':evaluated_fingerprint,
                     'rubric_digest':RULE_DIGEST, 'assessment':assessment,'current_stage':'completed','stage_errors':[]}
            conn.execute("UPDATE evaluation_runs SET status='completed',completed_at=now(),input_snapshot=input_snapshot || %s WHERE id=%s", (Jsonb(saved),run_id))
    except Exception as exc:
        with connection() as conn, conn.transaction():
            conn.execute(
                "UPDATE evaluation_runs SET status='failed',error_message=%s,completed_at=now() WHERE id=%s",
                (str(exc)[:4000], run_id),
            )
        raise
    print(f"EVALUATION_RUN_COMPLETE {run_id}", flush=True)
    return run_id


if __name__ == "__main__":
    run_all()
