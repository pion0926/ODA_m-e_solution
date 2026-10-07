from __future__ import annotations
import uuid
from fastapi import BackgroundTasks, HTTPException, Request
from psycopg.types.json import Jsonb
from ..db import connection, current_project_id
from ..evaluation_criteria import EVALUATION_CRITERIA
from ..localized_views import ViewTranslationError, localize_project_views
from ..pdm_jobs import serialize as serialize_pdm_refresh
from ..project_i18n import get_project_i18n, resolve_project_locale, set_preferred_locale
from ..settings import OPENROUTER_API_KEY
from ..project_overview import latest_plan_overview
from ..project_lifecycle import lock_project_workflow, project_lifecycle
from ..workflow_queue import enqueue
from .dependencies import _clean_risk_payload, _request_llm_model
from .schemas import PerformanceReviewRequest, ProjectLocaleUpdate
from .evaluation_routes import latest_evaluations
from fastapi import APIRouter
router = APIRouter()


@router.get("/api/v2/project/i18n")
def project_i18n():
    return get_project_i18n()


@router.post('/api/v2/project/translations/{job_id}/{action}')
def translation_action(job_id: uuid.UUID, action: str, request: Request):
    if action not in ('cancel', 'retry'):
        raise HTTPException(404, '지원하지 않는 작업입니다.')
    with connection() as conn, conn.transaction():
        row = conn.execute('SELECT * FROM translation_jobs WHERE id=%s FOR UPDATE', (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, '번역 작업이 없습니다.')
        if action == 'cancel' and row['status'] in ('queued', 'running'):
            conn.execute("UPDATE translation_jobs SET status='cancelled',completed_at=now() WHERE id=%s", (job_id,))
            conn.execute("UPDATE workflow_tasks SET status='cancelled',completed_at=now() WHERE kind='translation' AND arguments->>0=%s AND status='queued'", (str(job_id),))
        elif action == 'retry' and row['status'] in ('failed', 'cancelled'):
            if conn.execute("SELECT 1 FROM workflow_tasks WHERE kind='translation' AND arguments->>0=%s AND status='running'", (str(job_id),)).fetchone():
                raise HTTPException(409, '현재 요청이 종료된 후 재요청해 주세요.')
            conn.execute("UPDATE translation_jobs SET status='queued',error_message=NULL,completed_at=NULL WHERE id=%s", (job_id,))
            enqueue(conn, 'translation', [job_id], _request_llm_model(request))
    return {'status': 'accepted'}


@router.put("/api/v2/project/i18n/locale")
def project_i18n_locale(payload: ProjectLocaleUpdate):
    return set_preferred_locale(payload.locale)


@router.get("/healthz")
def healthz():
    with connection() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ok": True, "service": "kodame-api", "version": "2.4", "llm_configured": bool(OPENROUTER_API_KEY)}


@router.get("/api/v2")
def api_root(request: Request):
    return {"name": "K-ODAME API", "version": "v2.4", "status": "active", "model": _request_llm_model(request)}


@router.get("/api/v2/dashboard")
def dashboard():
    with connection() as conn:
        project_row = conn.execute(
            "SELECT name,is_bootstrap FROM projects WHERE id=%s",
            (current_project_id(),),
        ).fetchone()
        document_stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE (status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed'))) AS processing,
                      coalesce(sum(size_bytes),0) AS total_bytes
               FROM evaluation_intake_documents"""
        ).fetchone()
        assigned = conn.execute("SELECT count(DISTINCT document_id) AS count FROM document_slot_assignments").fetchone()["count"]
        run = conn.execute(
            "SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        evaluations = conn.execute(
            "SELECT criterion_id,criterion_name,score,question_assessments,evidence_gaps FROM criterion_evaluations WHERE run_id=%s ORDER BY id",
            (run["id"],),
        ).fetchall() if run else []
        overview_row = latest_plan_overview(conn)
        active_run = conn.execute(
            "SELECT status FROM evaluation_runs WHERE status IN ('queued','running') ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        report_stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='draft' AND content<>'') AS ready
                 FROM report_sections"""
        ).fetchone()
        lifecycle = project_lifecycle(conn)
        from ..evaluation_versions import current_bundle
        approved = bool(conn.execute('SELECT 1 FROM evaluation_versions WHERE revision=%s',
            (current_bundle(conn)['revision'],)).fetchone()) if lifecycle['report_current'] else False

    total = document_stats["total"]
    completed = document_stats["completed"]
    collection_pct = round(completed / total * 100) if total else 0
    classification_pct = round(assigned / total * 100) if total else 0
    judgement_pct = round(len(evaluations) / len(EVALUATION_CRITERIA) * 100)
    alerts = []
    gap_count = 0
    action_count = 0
    for criterion in evaluations:
        for question in criterion["question_assessments"]:
            gaps = question.get("evidence_gaps", [])
            actions = question.get("action_items", [])
            gap_count += len(gaps)
            action_count += len(actions)
            question_title = question.get("question", "")
            for item in gaps:
                alerts.append({
                    "severity": "critical" if question.get('score') is not None and float(question['score']) <= 2 else "warning",
                    "type": "자료 보완",
                    "criterion": criterion["criterion_name"],
                    "title": question_title,
                    "detail": item,
                })
            for item in actions:
                alerts.append({
                    "severity": "warning",
                    "type": "추가 조치",
                    "criterion": criterion["criterion_name"],
                    "title": question_title,
                    "detail": item,
                })
    review_pct = 100 if approved else 0
    steps = [
        {"name": "자료수집", "percent": collection_pct, "hint": f"업로드 문서 {completed}/{total}건 분석 완료"},
        {"name": "기준별 판단", "percent": judgement_pct, "hint": f"평가기준 {len(evaluations)}/{len(EVALUATION_CRITERIA)}개 분석 완료"},
        {"name": "자료 분류 정리", "percent": classification_pct, "hint": f"문서 {assigned}/{total}건 기준별 슬롯 배정"},
        {"name": "제출 전 검토", "percent": review_pct, "hint": "현재 버전 검토 승인 완료" if approved else f"출처·결론 검토 승인 필요 · 자료 공백 {gap_count}건 · 추가 조치 {action_count}건"},
    ]
    progress = round(sum(step["percent"] for step in steps) / len(steps))
    overview = overview_row["overview"] if overview_row else {}
    value = lambda key, fallback: (overview.get(key) or {}).get("text") or fallback
    # Even the bootstrap workspace must derive business facts from its data.
    legacy_defaults: dict[str, str] = {}
    processing_documents = int(document_stats["processing"] or 0)
    is_empty = total == 0 and not run and not overview_row
    if is_empty:
        workflow_status = {"code": "empty_project", "message": "자료를 업로드해 주세요"}
    elif processing_documents:
        workflow_status = {"code": "processing_documents", "message": f"문서 {processing_documents}건 분석 진행 중"}
    elif active_run:
        workflow_status = {"code": "evaluation_active", "message": "전체 문서 평가 분석 중"}
    elif not lifecycle["evaluation_current"]:
        workflow_status = {"code": "evaluation_required", "message": "전체 문서 재평가 필요"}
    elif alerts:
        workflow_status = {"code": "review_required", "message": f"보완 {len(alerts)}건 검토 필요"}
    elif not lifecycle["report_current"]:
        workflow_status = {"code": "report_required", "message": "평가보고서 초안 작성 필요"}
    elif not approved:
        workflow_status = {"code": "approval_required", "message": "출처 충실성·결론 타당성 검토 승인 필요"}
    else:
        workflow_status = {"code": "ready", "message": "제출 준비 완료"}
    return {
        "lifecycle": lifecycle,
        "project": {
            # The workspace label is the canonical UI identity. A business
            # name extracted from uploaded documents is useful metadata, but
            # must not replace the selected project's name in navigation or
            # report headers.
            "name": project_row["name"] if project_row else "새 ODA 평가 프로젝트",
            "business_name": value("project_name", ""),
            "country": value("country", legacy_defaults.get("country", "")),
            "period": value("period", legacy_defaults.get("period", "")),
            "budget": value("budget", legacy_defaults.get("budget", "")),
            "donor": value("donor", legacy_defaults.get("donor", "")),
            "implementer": value("implementer", legacy_defaults.get("implementer", "")),
        },
        "is_empty": is_empty,
        "document_count": total,
        "progress": progress,
        "steps": steps,
        "alerts": alerts,
        "gap_count": gap_count,
        "action_count": action_count,
        "workflow_status": workflow_status,
        "processing_document_count": processing_documents,
        "updated_at": run["completed_at"].isoformat() if run else None,
    }


@router.get("/api/v2/project-overview")
def project_overview():
    with connection() as conn:
        row = latest_plan_overview(conn)
        pdm_source = conn.execute(
            """SELECT d.id,d.original_name,d.size_bytes,d.summary
                 FROM pdm_models p JOIN evaluation_intake_documents d ON d.id=p.source_document_id
                ORDER BY p.created_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return {
                "status": "not_generated", "overview": None, "sources": {}, "conflicts": [],
                "project_plan_source_document": None,
                "pdm_source_document": {
                    "id": str(pdm_source["id"]), "file_name": pdm_source["original_name"],
                    "size_bytes": pdm_source["size_bytes"], "summary": pdm_source["summary"],
                } if pdm_source else None,
            }
        document_ids = row["source_document_ids"]
        documents = conn.execute("SELECT id,original_name,size_bytes,summary,upload_role FROM evaluation_intake_documents").fetchall()
    by_id = {str(item["id"]): item for item in documents}
    ref_map = {}
    for index, document_id in enumerate(document_ids, 1):
        document_id = str(document_id)
        item = by_id.get(document_id)
        if item:
            ref_map[f"D{index:03d}"] = {
                "id": document_id, "file_name": item["original_name"],
                "size_bytes": item["size_bytes"], "summary": item["summary"],
            }
    sources = {}
    # Link the source of this overview, never an independently selected PDM.
    plan_source = next((source for source in ref_map.values()
                        if by_id[source["id"]]["upload_role"] == "project_plan"), None)
    for field, item in row["overview"].items():
        sources[field] = [ref_map[ref] for ref in item.get("source_refs", []) if ref in ref_map]
    return {
        "status": "completed", "id": str(row["id"]),
        "run_id": str(row["run_id"]) if row["run_id"] else None,
        "model": row["model"], "document_count": row["document_count"],
        "overview": row["overview"], "sources": sources, "conflicts": row["conflicts"],
        "project_plan_source_document": plan_source,
        "pdm_source_document": {
            "id": str(pdm_source["id"]), "file_name": pdm_source["original_name"],
            "size_bytes": pdm_source["size_bytes"], "summary": pdm_source["summary"],
        } if pdm_source else None,
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/api/v2/pdm")
def pdm_monitoring():
    with connection() as conn:
        row = conn.execute("SELECT * FROM pdm_models ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return {
                "status": "not_generated", "source_document": None, "tiers": [],
                "performance_indicators": [], "coverage": {"filled": 0, "total": 0, "percent": 0},
                "assignments": [],
            }
        documents = conn.execute(
            "SELECT id,original_name,size_bytes,summary,analysis FROM evaluation_intake_documents ORDER BY queue_position"
        ).fetchall()
        assignments = conn.execute(
            """SELECT a.*,d.original_name,d.size_bytes,d.summary
                 FROM pdm_document_assignments a
                 JOIN evaluation_intake_documents d ON d.id=a.document_id
                ORDER BY a.tier,a.indicator_id,d.original_name"""
        ).fetchall()
    from ..pdm_mapping_policy import decision
    docs_by_id = {str(d['id']): d for d in documents}
    assignments = [a for a in assignments if decision(docs_by_id[str(a['document_id'])], a['indicator_id'], row['source_document_id'])]
    document_map = {
        str(item["id"]): {
            "id": str(item["id"]), "file_name": item["original_name"],
            "size_bytes": item["size_bytes"], "summary": item["summary"],
        }
        for item in documents
    }
    assignment_items = [{
        **item, "document_id": str(item["document_id"]),
        "confidence": float(item["confidence"]), "created_at": item["created_at"].isoformat(),
    } for item in assignments]
    by_indicator: dict[str, list[dict]] = {}
    for item in assignment_items:
        by_indicator.setdefault(item["indicator_id"], []).append(document_map[item["document_id"]])

    from ..document_eligibility import filter_performance_model
    model = filter_performance_model(row['model'], document_map)
    tiers = []
    filled = 0
    for tier in model.get("tiers", []):
        indicators = []
        for indicator in tier.get("indicators", []):
            evidence_documents = by_indicator.get(indicator["id"], [])
            if evidence_documents:
                filled += 1
            indicators.append({**indicator, "evidence_documents": evidence_documents,
                               "evidence_status": "secured" if evidence_documents else "missing"})
        tiers.append({**tier, "indicators": indicators})
    total = sum(len(tier["indicators"]) for tier in tiers)
    performance = []
    for indicator in model.get("performance_indicators", []):
        evidence = by_indicator.get(indicator["id"], [])
        cleaned_indicator = dict(indicator)
        removed_links = set(indicator.get('evidence_document_ids', [])) - {d['id'] for d in evidence}
        if removed_links:
            cleaned_indicator['mapping_review_required'] = True
            cleaned_indicator['note'] = '증빙 목적 기준으로 연결을 정리했습니다. 표시된 실적은 이전 분석 결과이며 재평가가 필요할 수 있습니다. ' + indicator.get('note','')
        cleaned_indicator["risk_analysis"] = _clean_risk_payload(indicator.get("risk_analysis") or {})
        performance.append({**cleaned_indicator, "evidence_documents": evidence, "evidence_document_ids": [d["id"] for d in evidence]})
    source_document = document_map.get(str(row["source_document_id"]))
    performance_source = document_map.get(str(model.get("performance_source_document_id") or ""))
    return {
        "status": "completed", "id": str(row["id"]), "source_document": source_document,
        "source_file_name": row["source_file_name"], "pdm_version": row["pdm_version"],
        "source_cells": model.get("source_cells", {}), "tiers": tiers,
        "performance_indicators": performance, "performance_source_document": performance_source,
        "monitoring": model.get("monitoring", {}),
        "risk_analysis": model.get("risk_analysis", {}),
        "coverage": {
            "filled": filled, "total": total,
            "percent": round(filled / max(1, total) * 100),
            "complete_tiers": sum(1 for tier in tiers if tier["indicators"] and all(item["evidence_documents"] for item in tier["indicators"])),
            "tier_total": len(tiers),
        },
        "assignments": assignment_items, "created_at": row["created_at"].isoformat(),
    }


@router.get("/api/v2/pdm/refresh/status")
def pdm_refresh_status():
    with connection() as conn:
        row = conn.execute('SELECT * FROM pdm_refresh_runs ORDER BY started_at DESC LIMIT 1').fetchone()
    return serialize_pdm_refresh(row)


@router.get('/api/v2/pdm/analysis-plan')
def performance_analysis_plan():
    from ..performance_review import build_plan
    return build_plan()


@router.post("/api/v2/pdm/refresh", status_code=202)
def refresh_pdm(request: Request, background_tasks: BackgroundTasks, review: PerformanceReviewRequest | None = None):
    from ..project_lifecycle import lock_project_workflow
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        lock_project_workflow(conn)
        active = conn.execute("SELECT * FROM pdm_refresh_runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
        if active:
            return serialize_pdm_refresh(active)
        if conn.execute("SELECT id FROM evaluation_runs WHERE status IN ('queued','running') LIMIT 1").fetchone():
            raise HTTPException(409, 'DAC 평가 중에는 PDM을 별도로 갱신할 수 없습니다. 평가 완료 후 다시 시도해 주세요.')
        if conn.execute("SELECT id FROM evaluation_intake_documents WHERE (status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed')) LIMIT 1").fetchone():
            raise HTTPException(409, '문서 분석이 모두 완료된 뒤 지표를 갱신해 주세요.')
        from ..performance_review import build_plan, validate_selection, save_overrides
        if review is None:
            raise HTTPException(409, '성과지표 분석 개요와 문서 매핑을 먼저 확인해 주세요.')
        current = build_plan(conn)
        reviewed = validate_selection(current, review.revision, review.mappings)
        save_overrides(conn, current, reviewed)
        run_id = uuid.uuid4()
        row = conn.execute("INSERT INTO pdm_refresh_runs(id,model,analysis_plan) VALUES (%s,%s,%s) RETURNING *",
                           (run_id,selected_model,Jsonb(reviewed))).fetchone()
        enqueue(conn, 'pdm', [run_id], selected_model)
    return serialize_pdm_refresh(row)


@router.get("/api/v2/project/i18n/views")
def localized_dashboard_and_project_overview(locale: str | None = None):
    selected_locale, source_locale = resolve_project_locale(locale)
    views = {
        "dashboard": dashboard(),
        "project_overview": project_overview(),
        "pdm": pdm_monitoring(),
        "evaluation": latest_evaluations(),
    }
    try:
        from ..translation_jobs import request_translation
        return request_translation(
            views,
            locale=selected_locale,
            source_locale=source_locale,
        )
    except ViewTranslationError as exc:
        raise HTTPException(503, f"화면 전체 번역을 완료하지 못했습니다: {exc}") from exc
