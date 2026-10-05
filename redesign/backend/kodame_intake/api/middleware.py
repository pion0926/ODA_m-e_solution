from __future__ import annotations
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from ..admin import has_menu_permission, mutation_menu_permission
from ..auth import load_session
from ..db import tenant_context
from ..llm_models import llm_model_context
from ..project_ai import get_project_model
from ..settings import SESSION_COOKIE_NAME
from .dependencies import ACCOUNT_ONLY_API_PATHS, PUBLIC_API_PATHS, REPORT_API_PREFIX


async def account_scope(request: Request, call_next):
    session = await run_in_threadpool(load_session, request.cookies.get(SESSION_COOKIE_NAME))
    request.state.auth = session
    protected = request.url.path.startswith("/api/v2") and request.url.path not in PUBLIC_API_PATHS
    if protected and not session:
        return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
    account_only = request.url.path in ACCOUNT_ONLY_API_PATHS or request.url.path.startswith("/api/v2/account/projects")
    admin_only = request.url.path.startswith("/api/v2/admin/")
    if protected:
        expected_account = request.headers.get("x-odame-account")
        expected_project = request.headers.get("x-odame-project")
        account_changed = expected_account is not None and expected_account != str(session["account_id"])
        project_changed = expected_project is not None and expected_project != str(session.get("project_id") or "")
        if account_changed or (not admin_only and not account_only and project_changed):
            return JSONResponse({"code": "workspace_changed", "detail": "계정 또는 프로젝트가 다른 탭에서 변경되었습니다. 입력 내용을 보관한 후 현재 작업 공간을 다시 열어 주세요."}, status_code=409)
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
        try:
            model = await run_in_threadpool(get_project_model) if protected and session.get("project_id") and not admin_only else None
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        request.state.llm_model = model
        with llm_model_context(model):
            return await call_next(request)
