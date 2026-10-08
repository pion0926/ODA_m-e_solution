from __future__ import annotations
import uuid
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from ..account_settings import get_account_settings
from ..admin import create_project, list_accounts, list_projects, login_history, require_admin, update_menu_permissions
from ..auth import auth_payload, clear_session_cookie, create_session, load_session, login, register_account, revoke_session, set_session_cookie
from ..db import tenant_context
from ..project_ai import update_project_model
from ..model_catalog import get_model_catalog
from ..report_sections import sync_report_sections
from ..settings import ALLOW_REGISTRATION, SESSION_COOKIE_NAME
from .dependencies import _request_account_id
from .schemas import AccountSettingsUpdate, LoginRequest, MenuPermissionsUpdate, ProjectAIUpdate, ProjectCreateRequest, RegistrationRequest
from fastapi import APIRouter
router = APIRouter()


@router.post("/api/v2/auth/login")
def auth_login(payload: LoginRequest, request: Request):
    account = login(payload.email, payload.password)
    token, _ = create_session(account["id"], request)
    session = load_session(token)
    response = JSONResponse(auth_payload(session))
    set_session_cookie(response, token)
    return response


@router.post("/api/v2/auth/register", status_code=201)
def auth_register(payload: RegistrationRequest, request: Request):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "신규 계정 등록이 비활성화되어 있습니다.")
    account_id = register_account(payload.email, payload.password, payload.display_name)
    token, _ = create_session(account_id, request)
    session = load_session(token)
    response = JSONResponse(auth_payload(session), status_code=201)
    set_session_cookie(response, token)
    return response


@router.get("/api/v2/auth/me")
def auth_me(request: Request):
    if not request.state.auth:
        raise HTTPException(401, "로그인이 필요합니다.")
    return auth_payload(request.state.auth)


@router.get("/api/v2/account/settings")
def account_settings(request: Request):
    return get_account_settings(_request_account_id(request))


@router.put("/api/v2/account/settings")
def save_account_settings(payload: AccountSettingsUpdate, request: Request):
    raise HTTPException(403, "AI 모델은 관리자가 프로젝트 관리에서 배정합니다. 계정별로 변경할 수 없습니다.")


@router.get("/api/v2/admin/ai-models")
def admin_ai_models(request: Request, refresh: bool = False):
    require_admin(request.state.auth)
    return get_model_catalog(refresh=refresh)


@router.put("/api/v2/admin/projects/{project_id}/ai-model")
def admin_project_ai(project_id: uuid.UUID, payload: ProjectAIUpdate, request: Request):
    require_admin(request.state.auth)
    return update_project_model(project_id, payload.llm_model, payload.expected_revision, _request_account_id(request))


@router.get("/api/v2/admin/accounts")
def admin_accounts(request: Request):
    require_admin(request.state.auth)
    return list_accounts()


@router.get("/api/v2/admin/projects")
def admin_projects(request: Request):
    require_admin(request.state.auth)
    return list_projects()


@router.post("/api/v2/admin/projects", status_code=201)
def admin_create_project(payload: ProjectCreateRequest, request: Request):
    require_admin(request.state.auth)
    created = create_project(
        request.state.auth["account_id"], payload.name, payload.supported_locales,
        payload.default_locale, payload.account_ids,
    )
    with tenant_context(created["id"], account_id=request.state.auth["account_id"]):
        sync_report_sections()
    return created


@router.put("/api/v2/admin/accounts/{account_id}/menus")
def admin_account_menus(account_id: str, payload: MenuPermissionsUpdate, request: Request):
    require_admin(request.state.auth)
    return update_menu_permissions(account_id, payload.menu_permissions)


@router.get("/api/v2/admin/accounts/{account_id}/login-history")
def admin_account_login_history(account_id: str, request: Request, limit: int = 20):
    require_admin(request.state.auth)
    return login_history(account_id, limit)


@router.post("/api/v2/auth/logout", status_code=204)
def auth_logout(request: Request):
    revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
