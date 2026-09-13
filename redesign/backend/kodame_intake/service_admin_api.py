"""Account issuance and explicit project selection, separate from report APIs."""
import secrets

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .admin import (
    assign_project_member, create_account, require_admin,
    reset_account_password, update_account_status,
)
from .auth import account_projects, auth_payload, load_session, select_project
from .project_lifecycle import project_lifecycle
from .settings import SESSION_COOKIE_NAME

router = APIRouter(prefix="/api/v2")


class AccountIssueRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str | None = Field(default=None, min_length=10, max_length=256)
    project_id: str = Field(min_length=36, max_length=36)
    display_name: str = Field(min_length=2, max_length=80)
    menu_permissions: dict[str, bool] | None = None


class AccountStatusRequest(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=10, max_length=256)


@router.post("/admin/accounts", status_code=201)
def issue_account(payload: AccountIssueRequest, request: Request, response: Response):
    require_admin(request.state.auth)
    password = payload.password or secrets.token_urlsafe(18)
    result = create_account(payload.username, password, payload.display_name, payload.menu_permissions, payload.project_id)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if payload.password is None:
        result["initial_password"] = password
    return result


@router.put("/admin/accounts/{account_id}/status")
def set_account_status(account_id: str, payload: AccountStatusRequest, request: Request):
    require_admin(request.state.auth)
    return update_account_status(account_id, payload.is_active)


@router.put("/admin/accounts/{account_id}/password")
def reset_password(account_id: str, payload: PasswordResetRequest, request: Request):
    require_admin(request.state.auth)
    return reset_account_password(account_id, payload.password)


@router.put("/admin/projects/{project_id}/members/{account_id}")
def assign_member(project_id: str, account_id: str, request: Request):
    require_admin(request.state.auth)
    return assign_project_member(project_id, account_id)


@router.delete("/admin/projects/{project_id}/members/{account_id}")
def remove_member(project_id: str, account_id: str, request: Request):
    require_admin(request.state.auth)
    return assign_project_member(project_id, account_id, remove=True)


@router.get("/account/projects")
def projects_for_account(request: Request):
    return account_projects(request.state.auth["account_id"])


@router.put("/account/projects/{project_id}/select")
def select_account_project(project_id: str, request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    select_project(token, request.state.auth["account_id"], project_id)
    return auth_payload(load_session(token))


@router.get("/project/lifecycle")
def get_project_lifecycle():
    return project_lifecycle()
