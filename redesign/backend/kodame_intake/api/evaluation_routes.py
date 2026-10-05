from __future__ import annotations
import uuid
from fastapi import BackgroundTasks, HTTPException, Request
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from ..db import connection, current_project_id
from ..evaluation_criteria import EVALUATION_CRITERIA, grade
from ..project_lifecycle import project_lifecycle
from ..workflow_queue import enqueue
from ..dac_improvement import build_improvement_guidance
from .dependencies import _request_llm_model, _reserve_project_workflow
from .schemas import DacReviewRequest
from fastapi import APIRouter
router = APIRouter()


@router.get("/api/v2/evaluations")
def latest_evaluations():
    with connection() as conn:
        run = conn.execute(
            "SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if not run:
            return {"status": "not_run", "criteria": [], "overall": None, "lifecycle": project_lifecycle(conn)}
        rows = conn.execute(
            "SELECT * FROM criterion_evaluations WHERE run_id=%s ORDER BY id", (run["id"],)
        ).fetchall()
        documents = conn.execute("SELECT id,original_name,size_bytes FROM evaluation_intake_documents").fetchall()
        lifecycle = project_lifecycle(conn)
    document_map = {str(row["id"]): {"id": str(row["id"]), "file_name": row["original_name"],
                                      "size_bytes": row["size_bytes"]} for row in documents}
    criteria = []
    for row in rows:
        assessments = []
        for assessment in row["question_assessments"]:
            evidence = [document_map[item] for item in assessment.get("evidence_document_ids", []) if item in document_map]
            assessments.append({**assessment, "evidence_documents": evidence})
        evidence = [document_map[item] for item in row["evidence_document_ids"] if item in document_map]
        criteria.append({
            "id": row["criterion_id"], "name": row["criterion_name"], "score": float(row["score"]) if row['score'] is not None else None,
            "summary": row["summary"], "score_reason": row["score_reason"],
            "question_assessments": assessments, "evidence_documents": evidence,
            "evidence_gaps": row["evidence_gaps"], "source_document_count": row["source_document_count"],
            "scored": row['score'] is not None,
            "assessment_status": 'proposed' if row['score'] is not None else 'needs_evidence_or_review',
        })
    for criterion in criteria:
        criterion['improvement_guidance'] = build_improvement_guidance(
            criterion, stale=lifecycle.get('evaluation_stale', False))
    total = round(sum(item["score"] for item in criteria), 1) if len(criteria) == 5 and all(i['scored'] for i in criteria) else None
    koica_grade, government_grade = grade(total) if total is not None else ('판정보류','판정보류')
    return {
        "status": "completed", "run_id": str(run["id"]), "model": run["model"],
        "lifecycle": lifecycle, "is_stale": lifecycle["evaluation_stale"],
        "document_count": run["document_count"], "completed_at": run["completed_at"].isoformat(),
        "pdm_context": (run.get("input_snapshot") or {}).get("pdm_context", {}),
        "rubric_digest": (run.get('input_snapshot') or {}).get('rubric_digest'),
        "reused_from_run_id": (run.get('input_snapshot') or {}).get('reused_from_run_id'),
        "criteria": criteria,
        "overall": {"score": total, "max_score": 20, "koica_grade": koica_grade,
                    "government_grade": government_grade,
                    "formula": "DAC 5개 기준의 질문별 1~4점 평균 합산"},
    }


@router.get("/api/v2/evaluations/status")
def evaluation_status():
    with connection() as conn:
        run = conn.execute(
            """SELECT r.*,
                      ((SELECT count(*) FROM criterion_evaluations c WHERE c.run_id=r.id) +
                       (SELECT count(*) FROM project_overviews p WHERE p.run_id=r.id)) AS completed_criteria
               FROM evaluation_runs r
               ORDER BY CASE WHEN status IN ('queued','running') THEN 0 ELSE 1 END, started_at DESC
               LIMIT 1"""
        ).fetchone()
        stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE (status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed'))) AS processing
                 FROM evaluation_intake_documents"""
        ).fetchone()
        lifecycle = project_lifecycle(conn)
    if not run:
        return {
            "status": "not_run", "active": False, "completed_criteria": 0,
            "lifecycle": lifecycle,
            "total_criteria": len(EVALUATION_CRITERIA) + 1,
            "document_count": stats["total"], "completed_document_count": stats["completed"],
            "processing_document_count": stats["processing"],
            "can_start": bool(stats["completed"]) and not bool(stats["processing"]),
        }
    return {
        "run_id": str(run["id"]), "status": run["status"],
        "lifecycle": lifecycle,
        "active": run["status"] in ("queued", "running"),
        "document_count": run["document_count"], "completed_criteria": run["completed_criteria"],
        "total_criteria": len(EVALUATION_CRITERIA) + 1, "error_message": run["error_message"],
        "started_at": run["started_at"].isoformat(),
        "completed_at": run["completed_at"].isoformat() if run["completed_at"] else None,
        "completed_questions": len((run.get('input_snapshot') or {}).get('question_checkpoints', {})),
        "total_questions": sum(len(c['questions']) for c in EVALUATION_CRITERIA.values()),
        "current_question": (run.get('input_snapshot') or {}).get('current_question'),
        "current_stage": (run.get('input_snapshot') or {}).get('current_stage'),
        "stage_errors": (run.get('input_snapshot') or {}).get('stage_errors',[]),
        "resumed_from_run_id": (run.get('input_snapshot') or {}).get('resumed_from_run_id'),
        "recovery_available": bool((run.get('input_snapshot') or {}).get('question_checkpoints')),
        "completed_document_count": stats["completed"],
        "processing_document_count": stats["processing"],
        "can_start": bool(stats["completed"]) and not bool(stats["processing"]) and not (run["status"] in ("queued", "running")),
    }


@router.get('/api/v2/evaluations/analysis-plan')
def dac_analysis_plan():
    from ..dac_review import build_plan
    return build_plan()


@router.post("/api/v2/evaluations", status_code=202)
def start_evaluation(background_tasks: BackgroundTasks, request: Request, review: DacReviewRequest | None = None):
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        from ..dac_review import build_plan, validate_selection
        if review is None:
            raise HTTPException(409, 'DAC 평가 계획과 질문별 문서를 먼저 확인해 주세요.')
        reviewed = validate_selection(build_plan(conn), review.revision, review.mappings, review.full_questions)
        stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE (status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed'))) AS processing
               FROM evaluation_intake_documents"""
        ).fetchone()
        if not stats["completed"]:
            raise HTTPException(409, "평가할 업로드 문서가 없습니다.")
        if stats["processing"]:
            raise HTTPException(409, f"문서 {stats['processing']}건이 아직 처리 중입니다. 처리가 끝난 후 재평가하세요.")
        active = conn.execute(
            "SELECT id,status FROM evaluation_runs WHERE status IN ('queued','running') ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if active:
            raise HTTPException(409, "전체 문서 재평가가 이미 진행 중입니다.")
        run_id = uuid.uuid4()
        try:
            conn.execute(
                "INSERT INTO evaluation_runs(id,status,model,document_count,input_snapshot) VALUES (%s,'queued',%s,%s,%s)",
                (run_id, selected_model, stats["completed"], Jsonb({'review_plan':reviewed})),
            )
        except UniqueViolation:
            raise HTTPException(409, "전체 문서 재평가가 이미 진행 중입니다.")
        project_id = current_project_id()
        enqueue(conn, 'dac', [run_id, project_id, selected_model], selected_model)
    return {"run_id": str(run_id), "status": "queued", "document_count": stats["completed"], "model": selected_model}
