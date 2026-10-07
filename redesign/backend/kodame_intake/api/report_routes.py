from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from ..db import connection, current_project_id
from ..llm_models import current_llm_model
from ..model_catalog import require_available_model
from ..report_generator import report_export_readiness
from ..report_resume import resumable_parts
from ..report_references import reference_stats
from ..report_exporter import EXPORT_DIR
from ..presentation_exporter import PRESENTATION_DIR
from ..presentation_profiles import PresentationRequest
from ..report_sections import sync_report_sections
from ..project_identity import current_project_identity, project_title_section
from ..report_sources import strip_inline_source_citations
from report_outline import canonical_narrative_outline_text
from backend.oda_me.hwpx.adapters.summary_ko import normalize_summary_ko_document
from backend.oda_me.reports.context import sanitize_editor_part_response
from ..settings import OPENROUTER_API_KEY, OPENROUTER_PRESENTATION_MODEL
from ..project_lifecycle import capture_input_snapshot, project_lifecycle
from ..workflow_queue import enqueue
from .dependencies import _request_llm_model, _reserve_project_workflow, serialize_generation_run, serialize_presentation_export, serialize_report_export, serialize_report_section
from .schemas import ReportGenerationRequest, ReportSectionUpdate
from fastapi import APIRouter
router = APIRouter()


@router.get("/api/v2/report/sections")
def list_report_sections():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM report_sections ORDER BY section_number").fetchall()
        identity = current_project_identity(conn)
    rows = [{**row, 'content': project_title_section(row['part_id'], row['content'], identity)} for row in rows]
    return {"items": [serialize_report_section(row) for row in rows], "count": len(rows)}


@router.get('/api/v2/report/job-tray')
def report_job_tray():
    """Small tenant-scoped job snapshot, without report text or navigation effects."""
    with connection() as conn:
        sections=conn.execute('SELECT part_id,title,status,error_message FROM report_sections').fetchall()
        items=[{'key':f"section:{s['part_id']}",'name':f"보고서 섹션 · {s['title']}",
                'active':s['status']=='generating','failed':s['status']=='failed',
                'detail':s['error_message'] or ('AI가 본문을 작성·검토하고 있습니다.' if s['status']=='generating' else '본문 저장 완료')} for s in sections]
        translations = conn.execute('SELECT id,locale,status,error_message FROM translation_jobs ORDER BY created_at DESC LIMIT 10').fetchall()
        for row in translations:
            active = row['status'] in ('queued', 'running')
            items.append({'key':f"translation:{row['id']}", 'documentId':f"translation:{row['id']}",
                'name':f"화면 번역 · {row['locale']}", 'active':active, 'failed':row['status']=='failed',
                'cancelled':row['status']=='cancelled', 'action':'cancel' if active else 'retry' if row['status'] in ('failed','cancelled') else None,
                'detail':row['error_message'] or ('번역 대기·진행 중 · 원래 언어로 화면을 계속 사용할 수 있습니다.' if active else '번역 '+row['status'])})
        for table,key,name,progress,total in (
            ('report_generation_runs','report','보고서 전체 작성','completed_sections','total_sections'),
            ('presentation_exports','presentation','AI 발표자료 작성','progress','100'),
            ('report_exports','export','HWPX 생성','progress','100')):
            order='started_at' if table=='report_generation_runs' else 'created_at'
            row=conn.execute(f'SELECT status,{progress} AS progress,{total} AS total,error_message,message FROM {table} ORDER BY {order} DESC LIMIT 1').fetchone()
            if row:
                items.append({'key':key,'name':name,'active':row['status'] in ('queued','running'),
                    'failed':row['status'] in ('failed','completed_with_errors'),'cancelled':row['status']=='cancelled',
                    'completed':row['progress'],'total':row['total'],
                    'detail':row['error_message'] or row['message'] or ('작업 진행 중' if row['status'] in ('queued','running') else '작업 종료')})
    return {'items':items}


@router.get("/api/v2/report/references/stats")
def get_report_reference_stats():
    return reference_stats()


@router.get("/api/v2/report/sections/{part_id}")
def get_report_section(part_id: str):
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_sections WHERE part_id=%s", (part_id,)).fetchone()
        if row and part_id in {'cover', 'grade', 'project-overview'}:
            row = {**row, 'content': project_title_section(part_id, row['content'], current_project_identity(conn))}
    if not row:
        raise HTTPException(404, "보고서 섹션을 찾을 수 없습니다.")
    return serialize_report_section(row, with_documents=True)


@router.put("/api/v2/report/sections/{part_id}")
def update_report_section(part_id: str, payload: ReportSectionUpdate):
    cleaned_content = strip_inline_source_citations(payload.content.strip())
    normalized_content = (
        sanitize_editor_part_response(cleaned_content, part_id)
        if part_id == "grade"
        else normalize_summary_ko_document(cleaned_content)
        if part_id == "summary-ko"
        else canonical_narrative_outline_text(part_id, cleaned_content)
    )
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        editing = conn.execute("SELECT status,updated_at FROM report_sections WHERE part_id=%s FOR UPDATE", (part_id,)).fetchone()
        if editing and editing["status"] == "generating":
            raise HTTPException(409, "AI 생성 중에는 저장할 수 없습니다. 생성이 끝나면 다시 저장해 주세요.")
        if editing and payload.expected_updated_at and editing["updated_at"].isoformat() != payload.expected_updated_at:
            raise HTTPException(409, "다른 창에서 이 섹션이 변경되었습니다. 현재 편집 내용은 유지됩니다. 최신 저장본을 확인한 뒤 다시 저장해 주세요.")
        row = conn.execute(
            """UPDATE report_sections SET content=%s,status='draft',error_message=NULL,
                      generation_model='manual-user-edit',generation_metadata=%s,
                      quality_score=NULL,quality_report=%s,updated_at=now()
               WHERE part_id=%s RETURNING *""",
            (normalized_content, Jsonb({"pipeline": "manual-edit-v2", "outline_normalized": normalized_content != payload.content.strip(),
                                       "input_snapshot": capture_input_snapshot(conn)}),
             Jsonb({"manual_review_required": True}), part_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "보고서 섹션을 찾을 수 없습니다.")
    return serialize_report_section(row, with_documents=True)


@router.post("/api/v2/report/sections/{part_id}/generate", status_code=202)
def start_report_section_generation(
    part_id: str, payload: ReportGenerationRequest, background_tasks: BackgroundTasks, request: Request,
):
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        lifecycle = project_lifecycle(conn)
        if not lifecycle["can_generate_report"]:
            raise HTTPException(409, lifecycle["message"])
        row = conn.execute("SELECT status FROM report_sections WHERE part_id=%s FOR UPDATE", (part_id,)).fetchone()
        if not row:
            raise HTTPException(404, "보고서 섹션을 찾을 수 없습니다.")
        if row["status"] == "generating":
            raise HTTPException(409, "이 섹션을 이미 생성 중입니다.")
        conn.execute(
            "UPDATE report_sections SET status='generating',error_message=NULL,updated_at=now() WHERE part_id=%s",
            (part_id,),
        )
        project_id = current_project_id()
        enqueue(conn, 'report_section', [part_id, payload.instruction, project_id, selected_model, payload.current_content], selected_model)
    return {"part_id": part_id, "status": "generating", "model": selected_model}


@router.post("/api/v2/report/refresh-current")
def refresh_current_report():
    # Never replace expert/edited drafts with the lightweight bootstrap text.
    sync_report_sections(force_bootstrap=False)
    return {"status": "completed", "message": "섹션 정의를 최신화했습니다. 저장된 전문가 초안은 보존했습니다."}


@router.post("/api/v2/report/generate-all", status_code=202)
def start_all_report_generation(background_tasks: BackgroundTasks, request: Request):
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE (status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed'))) AS processing
                 FROM evaluation_intake_documents"""
        ).fetchone()
        if not stats["completed"]:
            raise HTTPException(409, "보고서에 반영할 업로드 문서가 없습니다.")
        if stats["processing"]:
            raise HTTPException(409, f"문서 {stats['processing']}건이 아직 처리 중입니다. 처리가 끝난 후 보고서를 생성하세요.")
        evaluation = conn.execute(
            "SELECT id FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if not evaluation:
            raise HTTPException(409, "먼저 DAC 평가진단에서 현재 자료를 반영한 평가를 완료하세요.")
        lifecycle = project_lifecycle(conn)
        if not lifecycle["can_generate_report"]:
            raise HTTPException(409, lifecycle["message"])
        active = conn.execute("SELECT count(*) AS count FROM report_sections WHERE status='generating'").fetchone()["count"]
        if active:
            raise HTTPException(409, "이미 생성 중인 보고서 섹션이 있습니다.")
        existing = conn.execute("SELECT id FROM report_generation_runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
        if existing:
            raise HTTPException(409, "전체 보고서 재생성이 이미 진행 중입니다.")
        run_id = uuid.uuid4()
        conn.execute(
            """INSERT INTO report_generation_runs
               (id,status,total_sections,completed_sections,failed_sections,message,model,input_snapshot)
               VALUES (%s,'queued',27,0,0,'전체 보고서 생성 대기 중',%s,%s)""",
            (run_id, selected_model, Jsonb(capture_input_snapshot(conn))),
        )
        project_id = current_project_id()
        enqueue(conn, 'report_all', [run_id, project_id, selected_model], selected_model)
    return {"id": str(run_id), "status": "queued", "section_count": 27,
            "pipeline": "expert-two-pass-v4", "model": selected_model}


@router.get("/api/v2/report/generation/latest")
def latest_report_generation():
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_generation_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    return serialize_generation_run(row) if row else {"status": "not_started", "total_sections": 27, "completed_sections": 0, "failed_sections": 0}


@router.post("/api/v2/report/generation/{run_id}/cancel")
def cancel_report_generation(run_id: uuid.UUID):
    with connection() as conn, conn.transaction():
        row = conn.execute("SELECT * FROM report_generation_runs WHERE id=%s FOR UPDATE", (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, "보고서 생성 작업을 찾을 수 없습니다.")
        if row["status"] in ("queued", "running"):
            row = conn.execute(
                """UPDATE report_generation_runs SET cancel_requested=true,
                   message='중단 요청 접수 · 진행 중인 AI 응답을 정리한 뒤 중단합니다.',updated_at=now()
                   WHERE id=%s RETURNING *""", (run_id,)).fetchone()
    return serialize_generation_run(row)


@router.post("/api/v2/report/generation/{run_id}/resume", status_code=202)
def resume_report_generation(run_id: uuid.UUID, background_tasks: BackgroundTasks, request: Request):
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        previous = conn.execute("SELECT * FROM report_generation_runs WHERE id=%s FOR UPDATE", (run_id,)).fetchone()
        if not previous:
            raise HTTPException(404, "보고서 생성 작업을 찾을 수 없습니다.")
        latest = conn.execute("SELECT id FROM report_generation_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if latest["id"] != previous["id"]:
            raise HTTPException(409, "가장 최근 작업만 이어서 생성할 수 있습니다.")
        lifecycle = project_lifecycle(conn)
        if not lifecycle["can_generate_report"]:
            raise HTTPException(409, lifecycle["message"])
        snapshot = capture_input_snapshot(conn)
        sections = conn.execute("SELECT part_id,status,content,generation_metadata FROM report_sections FOR UPDATE").fetchall()
        try:
            preserved = resumable_parts(previous, sections, snapshot)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        try:
            # Existing sections retain their own generation model; newly
            # requested sections follow the current project model policy.
            selected_model = require_available_model(_request_llm_model(request))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        new_id = uuid.uuid4()
        conn.execute("""INSERT INTO report_generation_runs
            (id,status,total_sections,completed_sections,failed_sections,message,model,input_snapshot,resume_part_ids,resumed_from_run_id)
            VALUES (%s,'queued',27,%s,0,%s,%s,%s,%s,%s)""",
            (new_id, len(preserved), f"저장된 {len(preserved)}개 섹션 보존 · 나머지 이어서 생성 대기",
             selected_model, Jsonb(snapshot), Jsonb(preserved), run_id))
        project_id = current_project_id()
        enqueue(conn, 'report_all', [new_id, project_id, selected_model], selected_model)
    return {"id": str(new_id), "status": "queued", "preserved_sections": len(preserved), "model": selected_model}


@router.post("/api/v2/report/exports", status_code=202)
def start_report_export(background_tasks: BackgroundTasks, request: Request):
    readiness = report_export_readiness(current_project_id())
    if not readiness["ready"]:
        messages = [f"{item.get('title') or item['scope']}: {item['message']}" for item in readiness["issues"][:6]]
        remainder = len(readiness["issues"]) - len(messages)
        suffix = f" 외 {remainder}건" if remainder > 0 else ""
        raise HTTPException(409, "HWPX 생성 전 점검이 필요합니다. " + " / ".join(messages) + suffix)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        lifecycle = project_lifecycle(conn)
        if not lifecycle["report_current"]:
            raise HTTPException(409, lifecycle["message"])
        active = conn.execute("SELECT id FROM report_exports WHERE status IN ('queued','running') LIMIT 1").fetchone()
        if active:
            raise HTTPException(409, "HWPX 내보내기가 이미 진행 중입니다.")
        export_id = uuid.uuid4()
        conn.execute(
            """INSERT INTO report_exports(id,status,progress,stage,message)
               VALUES (%s,'queued',0,'queued','내보내기 작업 대기 중')""", (export_id,)
        )
        enqueue(conn, 'report_export', [export_id, current_project_id(), lifecycle['input_snapshot']], _request_llm_model(request))
    return {"id": str(export_id), "status": "queued", "progress": 0}


@router.get("/api/v2/report/exports/latest")
def latest_report_export():
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_exports ORDER BY created_at DESC LIMIT 1").fetchone()
    return serialize_report_export(row) if row else {"status": "not_started", "progress": 0}


@router.get("/api/v2/report/exports/latest-completed")
def latest_completed_report_export():
    with connection() as conn:
        row = conn.execute(
            """SELECT * FROM report_exports
               WHERE status='completed' AND output_path IS NOT NULL
               ORDER BY completed_at DESC LIMIT 1"""
        ).fetchone()
    if not row:
        raise HTTPException(404, "미리볼 수 있는 완료 HWPX 파일이 없습니다. 먼저 HWPX 저장을 실행해 주세요.")
    return serialize_report_export(row)


@router.get("/api/v2/report/exports/{export_id}")
def get_report_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_exports WHERE id=%s", (export_id,)).fetchone()
    if not row:
        raise HTTPException(404, "HWPX 내보내기 작업을 찾을 수 없습니다.")
    return serialize_report_export(row)


@router.get("/api/v2/report/exports/{export_id}/download")
def download_report_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_exports WHERE id=%s", (export_id,)).fetchone()
    if not row or row["status"] != "completed" or not row["output_path"]:
        raise HTTPException(409, "완료된 HWPX 파일이 없습니다.")
    path = Path(row["output_path"]).resolve()
    export_root = EXPORT_DIR.resolve()
    if export_root not in path.parents or not path.is_file():
        raise HTTPException(404, "내보낸 HWPX 파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="application/hwp+zip", filename=row["file_name"])


@router.post("/api/v2/report/exports/{export_id}/verify-rhwp-toc")
def verify_report_rhwp_toc(export_id: uuid.UUID, payload: dict):
    from ..report_rhwp_verification import finalize_rhwp_toc
    try:
        return serialize_report_export(finalize_rhwp_toc(export_id, payload))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/v2/report/presentations", status_code=202)
def start_presentation_export(background_tasks: BackgroundTasks, request: Request, options: PresentationRequest = PresentationRequest()):
    try:
        selected_model = require_available_model(OPENROUTER_PRESENTATION_MODEL)
    except ValueError as exc:
        raise HTTPException(409, f"발표자료 전용 모델 설정을 확인해 주세요: {exc}") from exc
    if not OPENROUTER_API_KEY:
        raise HTTPException(409, "OpenRouter API 키가 설정되지 않아 발표자료를 생성할 수 없습니다.")
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        lifecycle = project_lifecycle(conn)
        if not lifecycle["report_current"]:
            raise HTTPException(409, lifecycle["message"])
        section_state = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE length(trim(content)) > 0) AS completed
                 FROM report_sections"""
        ).fetchone()
        if section_state["total"] != 27 or section_state["completed"] != 27:
            raise HTTPException(409, "발표자료 생성 전 27개 보고서 섹션을 모두 작성·저장해 주세요.")
        active = conn.execute(
            "SELECT id FROM presentation_exports WHERE status IN ('queued','running') LIMIT 1"
        ).fetchone()
        if active:
            raise HTTPException(409, "발표자료 생성이 이미 진행 중입니다.")
        export_id = uuid.uuid4()
        conn.execute(
            """INSERT INTO presentation_exports(id,status,progress,stage,message,model,slide_count)
               VALUES (%s,'queued',0,'queued','샘플 기반 발표자료 생성 대기 중',%s,%s)""",
            (export_id, selected_model, options.slide_count),
        )
        project_id = current_project_id()
        enqueue(conn, 'presentation', [export_id, project_id, options.slide_count], selected_model)
    return {
        "id": str(export_id), "status": "queued", "progress": 0,
        "slide_count": options.slide_count, "model": selected_model,
    }


@router.get("/api/v2/report/presentations/latest")
def latest_presentation_export():
    with connection() as conn:
        row = conn.execute("SELECT * FROM presentation_exports ORDER BY created_at DESC LIMIT 1").fetchone()
    return serialize_presentation_export(row) if row else {
        "status": "not_started", "progress": 0, "slide_count": 15,
        "model": current_llm_model(),
    }


@router.get("/api/v2/report/presentations/{export_id}")
def get_presentation_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM presentation_exports WHERE id=%s", (export_id,)).fetchone()
    if not row:
        raise HTTPException(404, "발표자료 생성 작업을 찾을 수 없습니다.")
    return serialize_presentation_export(row)


@router.get("/api/v2/report/presentations/{export_id}/download")
def download_presentation_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM presentation_exports WHERE id=%s", (export_id,)).fetchone()
    if not row or row["status"] != "completed" or not row["output_path"]:
        raise HTTPException(409, "완료된 발표자료 파일이 없습니다.")
    path = Path(row["output_path"]).resolve()
    export_root = PRESENTATION_DIR.resolve()
    if export_root not in path.parents or not path.is_file():
        raise HTTPException(404, "생성된 발표자료 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=row["file_name"],
    )
