from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from .account_settings import get_account_settings, update_account_model
from .admin import (
    create_project,
    has_menu_permission,
    list_accounts,
    list_projects,
    login_history,
    mutation_menu_permission,
    require_admin,
    update_menu_permissions,
)
from .auth import (
    auth_payload,
    clear_session_cookie,
    create_session,
    load_session,
    login,
    register_account,
    revoke_session,
    set_session_cookie,
)
from .db import connection, current_project_id, open_pool, pool, tenant_context
from .document_slots import DOCUMENT_SLOTS
from .evaluation_criteria import EVALUATION_CRITERIA, grade
from .evaluation_runner import run_all
from .hwpx_pipeline import hwpx_authoring_contract
from .llm_models import llm_model_context
from .localized_views import ViewTranslationError, localize_project_views
from .openrouter import clean_risk_text
from .report_generator import generate_all_report_sections, generate_report_section, report_export_readiness
from .report_references import reference_stats
from .report_exporter import EXPORT_DIR, run_report_export
from .presentation_exporter import PRESENTATION_DIR, SLIDE_COUNT, run_presentation_export
from .presentation_profiles import PresentationRequest
from .presentation_reference_export import run_reference_export
from .pdm_monitoring import refresh_pdm_model
from .project_i18n import get_project_i18n, resolve_project_locale, set_preferred_locale
from .report_sections import section_documents, section_reference_route, sync_report_sections
from .report_sources import strip_inline_source_citations
from report_outline import canonical_narrative_outline_text
from backend.oda_me.hwpx.adapters.summary_ko import normalize_summary_ko_document
from backend.oda_me.reports.context import sanitize_editor_part_response
from .settings import (
    ALLOWED_EXTENSIONS,
    ALLOW_REGISTRATION,
    MAX_FILE_BYTES,
    OPENROUTER_API_KEY,
    OPENROUTER_PRESENTATION_MODEL,
    ORIGINALS_DIR,
    SESSION_COOKIE_NAME,
    TAXONOMY_VERSION,
)
from .service_admin_api import router as service_admin_router
from .report_preview_api import router as report_preview_router
from .project_lifecycle import (active_workflow_jobs, capture_input_snapshot, lock_project_workflow,
                                project_lifecycle, recover_interrupted_sections)
from .taxonomy import DAC_CRITERIA, SECTIONS

def clean_filename(name: str) -> str:
    base = Path(name or "document").name
    base = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", base).strip(" .")
    return base[:180] or "document"


def _clean_risk_payload(value):
    if isinstance(value, dict):
        return {key: _clean_risk_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_risk_payload(item) for item in value]
    if isinstance(value, str):
        return clean_risk_text(value)
    return value

def serialize_document(row: dict) -> dict:
    return {
        "id": str(row["id"]), "file_name": row["original_name"], "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "status": row["status"], "stage": row["stage"], "progress": row["progress"],
        "queue_position": row["queue_position"], "summary": row.get("summary"),
        "error_code": row.get("error_code"), "error_message": row.get("error_message"),
        "uploaded_at": row["uploaded_at"].isoformat(), "updated_at": row["updated_at"].isoformat(),
    }

@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    with tenant_context(system=True):
        with connection() as conn, conn.transaction():
            conn.execute(
                """UPDATE evaluation_runs
                   SET status='failed',error_message='API 재시작으로 재평가가 중단되었습니다. 다시 실행해 주세요.',completed_at=now()
                   WHERE status IN ('queued','running')"""
            )
            conn.execute(
                """UPDATE report_exports SET status='failed',stage='failed',message='API 재시작으로 내보내기 중단',
                   error_message='내보내기 작업 중 API가 재시작되었습니다. 다시 실행해 주세요.',completed_at=now(),updated_at=now()
                   WHERE status IN ('queued','running')"""
            )
            conn.execute(
                """UPDATE report_generation_runs SET status='failed',message='API 재시작으로 전체 생성 중단',
                   error_message='전체 보고서 생성 중 API가 재시작되었습니다. 다시 실행해 주세요.',completed_at=now(),updated_at=now()
                   WHERE status IN ('queued','running')"""
            )
            conn.execute(
                """UPDATE presentation_exports SET status='failed',stage='failed',message='API 재시작으로 발표자료 생성 중단',
                   error_message='발표자료 생성 중 API가 재시작되었습니다. 다시 실행해 주세요.',completed_at=now(),updated_at=now()
                   WHERE status IN ('queued','running')"""
            )
            recover_interrupted_sections(conn)
            projects = conn.execute("SELECT id FROM projects WHERE status='active'").fetchall()
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    for project in projects:
        with tenant_context(project["id"]):
            sync_report_sections()
    yield
    pool.close()

app = FastAPI(title="KODAME Redesign API", version="2.1", lifespan=lifespan)
app.include_router(service_admin_router)
app.include_router(report_preview_router)


SAMPLE_TEMPLATE_FILES = {
    "evaluation-report-hwpx": "5-1. 종료평가 결과보고서 양식.hwpx",
    "evaluation-report-hwp": "5-1. 종료평가 결과보고서 양식.hwp",
    "evaluation-grade-xlsx": "5-2. 종료평가 등급 결과표(엑셀버전).xlsx",
    "evaluation-lessons-pptx": "5-3. 분야별 평가 교훈 리포트 양식.pptx",
    "consultant-consent-hwp": "5-6. 현지 평가 컨설턴트 개인정보 수집 및 활용동의서_국영문.hwp",
    "evaluation-faq-hwp": "9. 평가업무수행 길라잡이 FAQ.hwp",
}


def _sample_template_root() -> Path:
    configured = Path(os.getenv("SAMPLES_DIR", "/app/samples"))
    if configured.is_dir():
        return configured.resolve()
    return (Path(__file__).resolve().parents[3] / "samples").resolve()


class ReportSectionUpdate(BaseModel):
    content: str = Field(max_length=200000)
    expected_updated_at: str | None = Field(default=None, max_length=80)


class ReportGenerationRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    current_content: str | None = Field(default=None, max_length=200000)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RegistrationRequest(LoginRequest):
    display_name: str = Field(min_length=2, max_length=80)


class AccountSettingsUpdate(BaseModel):
    llm_model: str = Field(min_length=3, max_length=120)


class MenuPermissionsUpdate(BaseModel):
    menu_permissions: dict[str, bool]


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    supported_locales: list[str] = Field(min_length=1, max_length=5)
    default_locale: str = Field(min_length=2, max_length=10)
    account_ids: list[str] = Field(default_factory=list, max_length=100)


class ProjectLocaleUpdate(BaseModel):
    locale: str = Field(min_length=2, max_length=10)


PUBLIC_API_PATHS = {
    "/healthz",
    "/api/v2/auth/login",
    "/api/v2/auth/register",
    "/api/v2/auth/logout",
    "/api/v2/auth/me",
}

ACCOUNT_ONLY_API_PATHS = {
    "/api/v2/account/settings",
}

REPORT_API_PREFIX = "/api/v2/report"


@app.middleware("http")
async def account_scope(request: Request, call_next):
    session = load_session(request.cookies.get(SESSION_COOKIE_NAME))
    request.state.auth = session
    protected = request.url.path.startswith("/api/v2") and request.url.path not in PUBLIC_API_PATHS
    if protected and not session:
        return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
    account_only = request.url.path in ACCOUNT_ONLY_API_PATHS or request.url.path.startswith("/api/v2/account/projects")
    admin_only = request.url.path.startswith("/api/v2/admin/")
    if protected and session.get("is_admin") and not (account_only or admin_only):
        return JSONResponse({"detail": "관리자는 프로젝트·사용자 관리 전용입니다. 사업 작업은 발급한 사용자 계정으로 로그인해 주세요."}, status_code=403)
    if protected and not session.get("project_id") and not (account_only or admin_only):
        return JSONResponse({"detail": "이 계정에 배정된 프로젝트가 없습니다."}, status_code=403)
    if protected and request.url.path.startswith(REPORT_API_PREFIX) and not has_menu_permission(session, "evaluation_report"):
        return JSONResponse(
            {"detail": "관리자페이지에서 '보고서 자동작성' 권한을 허용해야 합니다."},
            status_code=403,
        )
    mutation_permission = mutation_menu_permission(request.method, request.url.path)
    if protected and mutation_permission and not has_menu_permission(session, mutation_permission):
        return JSONResponse({"detail": "관리자페이지에서 해당 기능의 권한을 허용해야 합니다.",
                             "required_menu_permission": mutation_permission}, status_code=403)
    with tenant_context(session.get("project_id") if session else None, account_id=session.get("account_id") if session else None):
        return await call_next(request)


def _run_background_for_account(task, account_id, project_id, *args):
    with tenant_context(project_id, account_id=account_id):
        task(*args)


def _reserve_project_workflow(conn) -> None:
    lock_project_workflow(conn)
    if active_workflow_jobs(conn):
        raise HTTPException(409, "현재 프로젝트에서 평가·보고서 작업이 진행 중입니다. 완료 후 다시 실행해 주세요.")


@app.post("/api/v2/auth/login")
def auth_login(payload: LoginRequest, request: Request):
    account = login(payload.email, payload.password)
    token, _ = create_session(account["id"], request)
    session = load_session(token)
    response = JSONResponse(auth_payload(session))
    set_session_cookie(response, token)
    return response


@app.post("/api/v2/auth/register", status_code=201)
def auth_register(payload: RegistrationRequest, request: Request):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "신규 계정 등록이 비활성화되어 있습니다.")
    account_id = register_account(payload.email, payload.password, payload.display_name)
    token, _ = create_session(account_id, request)
    session = load_session(token)
    response = JSONResponse(auth_payload(session), status_code=201)
    set_session_cookie(response, token)
    return response


@app.get("/api/v2/auth/me")
def auth_me(request: Request):
    if not request.state.auth:
        raise HTTPException(401, "로그인이 필요합니다.")
    return auth_payload(request.state.auth)


def _request_account_id(request: Request):
    session = request.state.auth
    if not session:
        raise HTTPException(401, "로그인이 필요합니다.")
    return session["account_id"]


def _request_llm_model(request: Request) -> str:
    return get_account_settings(_request_account_id(request))["llm_model"]


@app.get("/api/v2/account/settings")
def account_settings(request: Request):
    return get_account_settings(_request_account_id(request))


@app.put("/api/v2/account/settings")
def save_account_settings(payload: AccountSettingsUpdate, request: Request):
    try:
        return update_account_model(_request_account_id(request), payload.llm_model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v2/admin/accounts")
def admin_accounts(request: Request):
    require_admin(request.state.auth)
    return list_accounts()


@app.get("/api/v2/admin/projects")
def admin_projects(request: Request):
    require_admin(request.state.auth)
    return list_projects()


@app.post("/api/v2/admin/projects", status_code=201)
def admin_create_project(payload: ProjectCreateRequest, request: Request):
    require_admin(request.state.auth)
    created = create_project(
        request.state.auth["account_id"], payload.name, payload.supported_locales,
        payload.default_locale, payload.account_ids,
    )
    with tenant_context(created["id"], account_id=request.state.auth["account_id"]):
        sync_report_sections()
    return created


@app.put("/api/v2/admin/accounts/{account_id}/menus")
def admin_account_menus(account_id: str, payload: MenuPermissionsUpdate, request: Request):
    require_admin(request.state.auth)
    return update_menu_permissions(account_id, payload.menu_permissions)


@app.get("/api/v2/admin/accounts/{account_id}/login-history")
def admin_account_login_history(account_id: str, request: Request, limit: int = 20):
    require_admin(request.state.auth)
    return login_history(account_id, limit)


@app.get("/api/v2/project/i18n")
def project_i18n():
    return get_project_i18n()


@app.put("/api/v2/project/i18n/locale")
def project_i18n_locale(payload: ProjectLocaleUpdate):
    return set_preferred_locale(payload.locale)


@app.post("/api/v2/auth/logout", status_code=204)
def auth_logout(request: Request):
    revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    response = JSONResponse(content=None, status_code=204)
    clear_session_cookie(response)
    return response

@app.get("/healthz")
def healthz():
    with connection() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ok": True, "service": "kodame-redesign-api", "version": "2.1", "llm_configured": bool(OPENROUTER_API_KEY)}

@app.get("/api/v2")
def api_root(request: Request):
    return {"name": "KODAME Redesign API", "version": "v2.1", "status": "active", "model": _request_llm_model(request)}

@app.get("/api/v2/dashboard")
def dashboard():
    with connection() as conn:
        project_row = conn.execute(
            "SELECT name,is_bootstrap FROM projects WHERE id=%s",
            (current_project_id(),),
        ).fetchone()
        document_stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE status<>'completed') AS processing,
                      coalesce(sum(size_bytes),0) AS total_bytes
               FROM intake_documents"""
        ).fetchone()
        assigned = conn.execute("SELECT count(DISTINCT document_id) AS count FROM document_slot_assignments").fetchone()["count"]
        run = conn.execute(
            "SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        evaluations = conn.execute(
            "SELECT criterion_id,criterion_name,score,question_assessments,evidence_gaps FROM criterion_evaluations WHERE run_id=%s ORDER BY id",
            (run["id"],),
        ).fetchall() if run else []
        overview_row = conn.execute("SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1").fetchone()
        active_run = conn.execute(
            "SELECT status FROM evaluation_runs WHERE status IN ('queued','running') ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        report_stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='draft' AND content<>'') AS ready
                 FROM report_sections"""
        ).fetchone()
        lifecycle = project_lifecycle(conn)

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
                    "severity": "critical" if int(question.get("score", 0)) <= 2 else "warning",
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
    review_pct = 100 if run and not alerts else 0
    steps = [
        {"name": "자료수집", "percent": collection_pct, "hint": f"업로드 문서 {completed}/{total}건 분석 완료"},
        {"name": "기준별 판단", "percent": judgement_pct, "hint": f"평가기준 {len(evaluations)}/{len(EVALUATION_CRITERIA)}개 분석 완료"},
        {"name": "자료 분류 정리", "percent": classification_pct, "hint": f"문서 {assigned}/{total}건 기준별 슬롯 배정"},
        {"name": "제출 전 검토", "percent": review_pct, "hint": f"자료 공백 {gap_count}건 · 추가 조치 {action_count}건 검토 필요" if alerts else "보완사항 검토 완료"},
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

@app.get("/api/v2/project-overview")
def project_overview():
    with connection() as conn:
        row = conn.execute("SELECT * FROM project_overviews ORDER BY created_at DESC LIMIT 1").fetchone()
        pdm_source = conn.execute(
            """SELECT d.id,d.original_name,d.size_bytes,d.summary
                 FROM pdm_models p JOIN intake_documents d ON d.id=p.source_document_id
                ORDER BY p.created_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return {
                "status": "not_generated", "overview": None, "sources": {}, "conflicts": [],
                "pdm_source_document": {
                    "id": str(pdm_source["id"]), "file_name": pdm_source["original_name"],
                    "size_bytes": pdm_source["size_bytes"], "summary": pdm_source["summary"],
                } if pdm_source else None,
            }
        document_ids = row["source_document_ids"]
        documents = conn.execute("SELECT id,original_name,size_bytes,summary FROM intake_documents").fetchall()
    by_id = {str(item["id"]): item for item in documents}
    ref_map = {}
    for index, document_id in enumerate(document_ids, 1):
        item = by_id.get(document_id)
        if item:
            ref_map[f"D{index:03d}"] = {
                "id": document_id, "file_name": item["original_name"],
                "size_bytes": item["size_bytes"], "summary": item["summary"],
            }
    sources = {}
    for field, item in row["overview"].items():
        sources[field] = [ref_map[ref] for ref in item.get("source_refs", []) if ref in ref_map]
    return {
        "status": "completed", "id": str(row["id"]),
        "run_id": str(row["run_id"]) if row["run_id"] else None,
        "model": row["model"], "document_count": row["document_count"],
        "overview": row["overview"], "sources": sources, "conflicts": row["conflicts"],
        "pdm_source_document": {
            "id": str(pdm_source["id"]), "file_name": pdm_source["original_name"],
            "size_bytes": pdm_source["size_bytes"], "summary": pdm_source["summary"],
        } if pdm_source else None,
        "created_at": row["created_at"].isoformat(),
    }


@app.get("/api/v2/pdm")
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
            "SELECT id,original_name,size_bytes,summary FROM intake_documents ORDER BY queue_position"
        ).fetchall()
        assignments = conn.execute(
            """SELECT a.*,d.original_name,d.size_bytes,d.summary
                 FROM pdm_document_assignments a
                 JOIN intake_documents d ON d.id=a.document_id
                ORDER BY a.tier,a.indicator_id,d.original_name"""
        ).fetchall()
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

    model = dict(row["model"])
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
        evidence = [document_map[item] for item in indicator.get("evidence_document_ids", []) if item in document_map]
        cleaned_indicator = dict(indicator)
        cleaned_indicator["risk_analysis"] = _clean_risk_payload(indicator.get("risk_analysis") or {})
        performance.append({**cleaned_indicator, "evidence_documents": evidence})
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


@app.post("/api/v2/pdm/refresh", status_code=202)
def refresh_pdm(request: Request):
    with llm_model_context(_request_llm_model(request)):
        model_id = refresh_pdm_model(analyze_risks=True)
    return {"status": "completed", "id": str(model_id)}

@app.get("/api/v2/intake/taxonomy")
def taxonomy():
    return {"version": TAXONOMY_VERSION, "dac_criteria": DAC_CRITERIA, "sections": [
        {"number": n, "id": sid, "title": title, "classification_rule": rule} for n, sid, title, rule in SECTIONS
    ]}

@app.post("/api/v2/intake/uploads", status_code=202)
async def upload_documents(request: Request, files: list[UploadFile] = File(...)):
    if not files or len(files) > 100:
        raise HTTPException(400, "한 번에 1~100개 파일을 선택하세요.")
    accepted = []
    for upload in files:
        safe_name = clean_filename(upload.filename or "document")
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(415, f"지원하지 않는 형식입니다: {safe_name}")
        document_id = uuid.uuid4()
        directory = ORIGINALS_DIR / str(current_project_id()) / str(document_id)
        directory.mkdir(parents=True, exist_ok=False)
        destination = directory / safe_name
        temporary = directory / ".uploading"
        digest = hashlib.sha256()
        size = 0
        try:
            async with aiofiles.open(temporary, "wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise HTTPException(413, f"파일 크기 제한을 초과했습니다: {safe_name}")
                    digest.update(chunk)
                    await output.write(chunk)
            os.replace(temporary, destination)
            try:
                os.chmod(destination, 0o440)
            except OSError:
                pass
            deduplicated = False
            with connection() as conn, conn.transaction():
                row = conn.execute(
                    """INSERT INTO intake_documents
                       (id,original_name,stored_path,media_type,extension,size_bytes,sha256,analysis_model,uploaded_by_account_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (project_id,original_name,sha256) DO NOTHING
                       RETURNING *""",
                    (document_id, safe_name, str(destination), upload.content_type, extension, size,
                     digest.hexdigest(), _request_llm_model(request), _request_account_id(request)),
                ).fetchone()
                if row:
                    conn.execute(
                        "INSERT INTO processing_events(document_id,stage,status,message,details) VALUES (%s,'queued','queued',%s,%s)",
                        (document_id, "원본 저장과 무결성 검증 후 처리 큐에 등록했습니다.", Jsonb({"sha256": digest.hexdigest()})),
                    )
                else:
                    row = conn.execute(
                        "SELECT * FROM intake_documents WHERE original_name=%s AND sha256=%s",
                        (safe_name, digest.hexdigest()),
                    ).fetchone()
                    deduplicated = True
            if deduplicated:
                shutil.rmtree(directory)
            accepted.append({**serialize_document(row), "deduplicated": deduplicated})
        except Exception:
            temporary.unlink(missing_ok=True)
            if not destination.exists():
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
        finally:
            await upload.close()
    return {"accepted": accepted, "count": len(accepted)}

@app.get("/api/v2/intake/jobs")
def list_jobs(limit: int = 100):
    limit = max(1, min(limit, 200))
    with connection() as conn:
        rows = conn.execute("SELECT * FROM intake_documents ORDER BY queue_position DESC LIMIT %s", (limit,)).fetchall()
    return {"items": [serialize_document(row) for row in rows], "count": len(rows), "worker_concurrency": 1}

@app.get("/api/v2/intake/jobs/{document_id}")
def get_job(document_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM intake_documents WHERE id=%s", (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, "문서를 찾을 수 없습니다.")
        events = conn.execute("SELECT stage,status,message,created_at FROM processing_events WHERE document_id=%s ORDER BY id", (document_id,)).fetchall()
    result = serialize_document(row)
    result["analysis"] = row.get("analysis")
    result["events"] = [{**event, "created_at": event["created_at"].isoformat()} for event in events]
    return result

@app.get("/api/v2/intake/jobs/{document_id}/download")
def download_original_document(document_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute(
            "SELECT original_name,stored_path,media_type FROM intake_documents WHERE id=%s",
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")

    path = Path(row["stored_path"]).resolve()
    originals_root = ORIGINALS_DIR.resolve()
    if originals_root not in path.parents or not path.is_file():
        raise HTTPException(404, "원본 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type=row.get("media_type") or "application/octet-stream",
        filename=row["original_name"],
    )


@app.get("/api/v2/samples/templates/{template_id}/download")
def download_sample_template(template_id: str):
    filename = SAMPLE_TEMPLATE_FILES.get(template_id)
    if not filename:
        raise HTTPException(404, "샘플서식을 찾을 수 없습니다.")
    root = _sample_template_root()
    path = (root / filename).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "샘플서식 파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)

@app.post("/api/v2/intake/jobs/{document_id}/retry", status_code=202)
def retry_job(document_id: uuid.UUID, request: Request):
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """UPDATE intake_documents SET status='retry',stage='queued',progress=CASE WHEN extracted_path IS NULL THEN 0 ELSE 45 END,
               analysis_model=%s,
               available_at=now(),error_code=NULL,error_message=NULL,updated_at=now()
               WHERE id=%s AND status IN ('failed','waiting_llm','retry') RETURNING *""",
            (_request_llm_model(request), document_id),
        ).fetchone()
    if not row:
        raise HTTPException(409, "현재 상태에서는 재시도할 수 없습니다.")
    return serialize_document(row)

@app.get("/api/v2/intake/suggestions")
def list_suggestions(status: str = "pending"):
    with connection() as conn:
        rows = conn.execute(
            """SELECT s.*,d.original_name,d.size_bytes,d.summary FROM slot_suggestions s
               JOIN intake_documents d ON d.id=s.document_id WHERE s.review_status=%s
               ORDER BY s.created_at DESC,s.confidence DESC""", (status,)
        ).fetchall()
    return {"items": [{**row, "document_id": str(row["document_id"]), "confidence": float(row["confidence"]),
                       "created_at": row["created_at"].isoformat(), "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None} for row in rows], "count": len(rows)}

@app.get("/api/v2/intake/document-slots")
def list_document_slots():
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.*,d.original_name,d.size_bytes,d.summary
               FROM document_slot_assignments a JOIN intake_documents d ON d.id=a.document_id
               ORDER BY a.criterion,a.slot_id,d.original_name"""
        ).fetchall()
    items = [{**row, "document_id": str(row["document_id"]), "confidence": float(row["confidence"]),
              "created_at": row["created_at"].isoformat()} for row in rows]
    criteria = [{"id": key, "name": value["name"], "need": value["need"],
                 "slots": [{"id": sid, "title": title} for sid, title in value["slots"]]}
                for key, value in DOCUMENT_SLOTS.items()]
    return {"criteria": criteria, "items": items, "count": len(items)}

@app.get("/api/v2/evaluations")
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
        documents = conn.execute("SELECT id,original_name,size_bytes FROM intake_documents").fetchall()
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
            "id": row["criterion_id"], "name": row["criterion_name"], "score": float(row["score"]),
            "summary": row["summary"], "score_reason": row["score_reason"],
            "question_assessments": assessments, "evidence_documents": evidence,
            "evidence_gaps": row["evidence_gaps"], "source_document_count": row["source_document_count"],
            "scored": True,
        })
    total = round(sum(item["score"] for item in criteria if item["scored"]), 1)
    koica_grade, government_grade = grade(total)
    return {
        "status": "completed", "run_id": str(run["id"]), "model": run["model"],
        "lifecycle": lifecycle, "is_stale": lifecycle["evaluation_stale"],
        "document_count": run["document_count"], "completed_at": run["completed_at"].isoformat(),
        "pdm_context": (run.get("input_snapshot") or {}).get("pdm_context", {}),
        "criteria": criteria,
        "overall": {"score": total, "max_score": 20, "koica_grade": koica_grade,
                    "government_grade": government_grade,
                    "formula": "DAC 5개 기준의 질문별 1~4점 평균 합산"},
    }


@app.get("/api/v2/project/i18n/views")
def localized_dashboard_and_project_overview(locale: str | None = None):
    selected_locale, source_locale = resolve_project_locale(locale)
    views = {
        "dashboard": dashboard(),
        "project_overview": project_overview(),
        "pdm": pdm_monitoring(),
        "evaluation": latest_evaluations(),
    }
    try:
        return localize_project_views(
            views,
            locale=selected_locale,
            source_locale=source_locale,
        )
    except ViewTranslationError as exc:
        raise HTTPException(503, f"화면 전체 번역을 완료하지 못했습니다: {exc}") from exc

@app.get("/api/v2/evaluations/status")
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
                      count(*) FILTER (WHERE status<>'completed') AS processing
                 FROM intake_documents"""
        ).fetchone()
        lifecycle = project_lifecycle(conn)
    if not run:
        return {
            "status": "not_run", "active": False, "completed_criteria": 0,
            "lifecycle": lifecycle,
            "total_criteria": len(EVALUATION_CRITERIA) + 1,
            "document_count": stats["total"], "completed_document_count": stats["completed"],
            "processing_document_count": stats["processing"],
            "can_start": bool(stats["total"]) and not bool(stats["processing"]),
        }
    return {
        "run_id": str(run["id"]), "status": run["status"],
        "lifecycle": lifecycle,
        "active": run["status"] in ("queued", "running"),
        "document_count": run["document_count"], "completed_criteria": run["completed_criteria"],
        "total_criteria": len(EVALUATION_CRITERIA) + 1, "error_message": run["error_message"],
        "started_at": run["started_at"].isoformat(),
        "completed_at": run["completed_at"].isoformat() if run["completed_at"] else None,
        "completed_document_count": stats["completed"],
        "processing_document_count": stats["processing"],
        "can_start": not bool(stats["processing"]) and not (run["status"] in ("queued", "running")),
    }

@app.post("/api/v2/evaluations", status_code=202)
def start_evaluation(background_tasks: BackgroundTasks, request: Request):
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE status<>'completed') AS processing
               FROM intake_documents"""
        ).fetchone()
        if not stats["total"]:
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
                "INSERT INTO evaluation_runs(id,status,model,document_count) VALUES (%s,'queued',%s,%s)",
                (run_id, selected_model, stats["completed"]),
            )
        except UniqueViolation:
            raise HTTPException(409, "전체 문서 재평가가 이미 진행 중입니다.")
    project_id = current_project_id()
    background_tasks.add_task(_run_background_for_account, run_all, _request_account_id(request), project_id, run_id, project_id, selected_model)
    return {"run_id": str(run_id), "status": "queued", "document_count": stats["completed"], "model": selected_model}


def serialize_report_section(row: dict, with_documents: bool = False) -> dict:
    result = {
        "part_id": row["part_id"], "section_number": row["section_number"],
        "section_id": row["section_id"], "title": row["title"], "prompt": row["prompt"],
        "required_inputs": row["required_inputs"], "content": row["content"], "status": row["status"],
        "source_document_ids": row["source_document_ids"], "generation_model": row["generation_model"],
        "generation_metadata": row.get("generation_metadata") or {},
        "quality_score": float(row["quality_score"]) if row.get("quality_score") is not None else None,
        "quality_report": row.get("quality_report") or {},
        "content_storage": "report_sections.content",
        "reference_contract": section_reference_route(row["part_id"]),
        "hwpx_contract": hwpx_authoring_contract(row["part_id"]),
        "error_message": row["error_message"],
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }
    if with_documents:
        result["documents"] = section_documents(row["part_id"])
    return result


@app.get("/api/v2/report/sections")
def list_report_sections():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM report_sections ORDER BY section_number").fetchall()
    return {"items": [serialize_report_section(row) for row in rows], "count": len(rows)}


@app.get("/api/v2/report/references/stats")
def get_report_reference_stats():
    return reference_stats()


@app.get("/api/v2/report/sections/{part_id}")
def get_report_section(part_id: str):
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_sections WHERE part_id=%s", (part_id,)).fetchone()
    if not row:
        raise HTTPException(404, "보고서 섹션을 찾을 수 없습니다.")
    return serialize_report_section(row, with_documents=True)


@app.put("/api/v2/report/sections/{part_id}")
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


@app.post("/api/v2/report/sections/{part_id}/generate", status_code=202)
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
    background_tasks.add_task(
        _run_background_for_account, generate_report_section, _request_account_id(request), project_id,
        part_id, payload.instruction, project_id, selected_model, payload.current_content,
    )
    return {"part_id": part_id, "status": "generating", "model": selected_model}


@app.post("/api/v2/report/refresh-current")
def refresh_current_report():
    # Never replace expert/edited drafts with the lightweight bootstrap text.
    sync_report_sections(force_bootstrap=False)
    return {"status": "completed", "message": "섹션 정의를 최신화했습니다. 저장된 전문가 초안은 보존했습니다."}


@app.post("/api/v2/report/generate-all", status_code=202)
def start_all_report_generation(background_tasks: BackgroundTasks, request: Request):
    selected_model = _request_llm_model(request)
    with connection() as conn, conn.transaction():
        _reserve_project_workflow(conn)
        stats = conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status='completed') AS completed,
                      count(*) FILTER (WHERE status<>'completed') AS processing
                 FROM intake_documents"""
        ).fetchone()
        if not stats["total"]:
            raise HTTPException(409, "보고서에 반영할 업로드 문서가 없습니다.")
        if stats["processing"]:
            raise HTTPException(409, f"문서 {stats['processing']}건이 아직 처리 중입니다. 처리가 끝난 후 보고서를 생성하세요.")
        evaluation = conn.execute(
            "SELECT id FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if not evaluation:
            raise HTTPException(409, "먼저 평가기준 탭에서 전체 문서 재평가를 완료하세요.")
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
               (id,status,total_sections,completed_sections,failed_sections,message,model)
               VALUES (%s,'queued',27,0,0,'전체 보고서 생성 대기 중',%s)""", (run_id, selected_model),
        )
    project_id = current_project_id()
    background_tasks.add_task(_run_background_for_account, generate_all_report_sections, _request_account_id(request), project_id, run_id, project_id, selected_model)
    return {"id": str(run_id), "status": "queued", "section_count": 27,
            "pipeline": "expert-two-pass-v4", "model": selected_model}


def serialize_generation_run(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "total_sections": row["total_sections"],
        "completed_sections": row["completed_sections"], "failed_sections": row["failed_sections"],
        "current_part_id": row["current_part_id"], "message": row["message"],
        "error_message": row["error_message"], "started_at": row["started_at"].isoformat(),
        "model": row.get("model"),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }


@app.get("/api/v2/report/generation/latest")
def latest_report_generation():
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_generation_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    return serialize_generation_run(row) if row else {"status": "not_started", "total_sections": 27, "completed_sections": 0, "failed_sections": 0}


def serialize_report_export(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "progress": row["progress"],
        "stage": row["stage"], "message": row["message"], "error_message": row["error_message"],
        "file_name": row["file_name"], "validation": row["validation"],
        "download_url": f"/api/v2/report/exports/{row['id']}/download" if row["status"] == "completed" else None,
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }


@app.post("/api/v2/report/exports", status_code=202)
def start_report_export(background_tasks: BackgroundTasks):
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
    background_tasks.add_task(run_report_export, export_id, current_project_id())
    return {"id": str(export_id), "status": "queued", "progress": 0}


@app.get("/api/v2/report/exports/latest")
def latest_report_export():
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_exports ORDER BY created_at DESC LIMIT 1").fetchone()
    return serialize_report_export(row) if row else {"status": "not_started", "progress": 0}


@app.get("/api/v2/report/exports/latest-completed")
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


@app.get("/api/v2/report/exports/{export_id}")
def get_report_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM report_exports WHERE id=%s", (export_id,)).fetchone()
    if not row:
        raise HTTPException(404, "HWPX 내보내기 작업을 찾을 수 없습니다.")
    return serialize_report_export(row)


@app.get("/api/v2/report/exports/{export_id}/download")
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


@app.post("/api/v2/report/exports/{export_id}/verify-rhwp-toc")
def verify_report_rhwp_toc(export_id: uuid.UUID, payload: dict):
    from .report_rhwp_verification import finalize_rhwp_toc
    try:
        return serialize_report_export(finalize_rhwp_toc(export_id, payload))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def serialize_presentation_export(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "progress": row["progress"],
        "stage": row["stage"], "message": row["message"], "error_message": row["error_message"],
        "file_name": row["file_name"], "model": row["model"], "slide_count": row.get("slide_count") or (row.get("validation") or {}).get("slide_count") or SLIDE_COUNT,
        "validation": row["validation"],
        "download_url": f"/api/v2/report/presentations/{row['id']}/download" if row["status"] == "completed" else None,
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }


@app.post("/api/v2/report/presentations", status_code=202)
def start_presentation_export(background_tasks: BackgroundTasks, request: Request, options: PresentationRequest = PresentationRequest()):
    if not OPENROUTER_API_KEY:
        raise HTTPException(409, "OpenRouter API 키가 설정되지 않아 Claude 발표자료를 생성할 수 없습니다.")
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
            (export_id, OPENROUTER_PRESENTATION_MODEL, options.slide_count),
        )
    project_id = current_project_id()
    background_tasks.add_task(_run_background_for_account, run_reference_export, _request_account_id(request), project_id, export_id, project_id, options.slide_count)
    return {
        "id": str(export_id), "status": "queued", "progress": 0,
        "slide_count": options.slide_count, "model": OPENROUTER_PRESENTATION_MODEL,
    }


@app.get("/api/v2/report/presentations/latest")
def latest_presentation_export():
    with connection() as conn:
        row = conn.execute("SELECT * FROM presentation_exports ORDER BY created_at DESC LIMIT 1").fetchone()
    return serialize_presentation_export(row) if row else {
        "status": "not_started", "progress": 0, "slide_count": 15,
        "model": OPENROUTER_PRESENTATION_MODEL,
    }


@app.get("/api/v2/report/presentations/{export_id}")
def get_presentation_export(export_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM presentation_exports WHERE id=%s", (export_id,)).fetchone()
    if not row:
        raise HTTPException(404, "발표자료 생성 작업을 찾을 수 없습니다.")
    return serialize_presentation_export(row)


@app.get("/api/v2/report/presentations/{export_id}/download")
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

@app.post("/api/v2/intake/suggestions/approve-all")
def approve_all_suggestions():
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """WITH approved AS (
                   UPDATE slot_suggestions
                      SET review_status='approved',reviewed_at=now()
                    WHERE review_status='pending'
                RETURNING id)
               SELECT count(*) AS count FROM approved"""
        ).fetchone()
    return {"status": "approved", "count": row["count"]}


@app.post("/api/v2/intake/suggestions/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: int):
    with connection() as conn, conn.transaction():
        row = conn.execute(
            "UPDATE slot_suggestions SET review_status='approved',reviewed_at=now() WHERE id=%s AND review_status='pending' RETURNING id,review_status,reviewed_at",
            (suggestion_id,),
        ).fetchone()
    if not row:
        raise HTTPException(409, "이미 검토됐거나 존재하지 않는 제안입니다.")
    return row
