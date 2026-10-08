from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from psycopg.errors import UniqueViolation

from .db import connection
from .security import (
    hash_password,
    hash_session_token,
    normalize_email,
    normalize_login_identity,
    validate_password,
    verify_password,
)
from .settings import AUTH_COOKIE_SECURE, SESSION_COOKIE_NAME, SESSION_TTL_HOURS


def _project_payload(row: dict) -> dict | None:
    if not row.get("project_id"):
        return None
    return {
        "id": str(row["project_id"]),
        "name": row["project_name"],
        "role": row["project_role"],
        "status": row["project_status"],
        "default_locale": row.get("project_default_locale") or "ko",
        "supported_locales": row.get("project_supported_locales") or ["ko"],
        "preferred_locale": row.get("project_preferred_locale") or row.get("project_default_locale") or "ko",
    }


def auth_payload(row: dict) -> dict:
    return {
        "account": {
            "id": str(row["account_id"]),
            "email": row["email"],
            "display_name": row["display_name"],
            "is_admin": bool(row.get("is_admin")),
            "menu_permissions": row.get("menu_permissions") or {},
        },
        "project": _project_payload(row),
        "has_project": bool(row.get("project_id")),
    }


def load_session(token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = hash_session_token(token)
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """SELECT a.id AS account_id,a.email,a.display_name,a.is_admin,a.menu_permissions,
                      selected.id AS project_id,selected.name AS project_name,
                      selected.role AS project_role,selected.status AS project_status,
                      selected.default_locale AS project_default_locale,
                      selected.supported_locales AS project_supported_locales,
                      selected.preferred_locale AS project_preferred_locale
               FROM auth_sessions s
               JOIN accounts a ON a.id=s.account_id AND a.is_active=true
               LEFT JOIN LATERAL (
                 SELECT p.id,p.name,p.status,p.default_locale,p.supported_locales,pm.role,pm.preferred_locale
                 FROM project_members pm JOIN projects p ON p.id=pm.project_id
                 WHERE pm.account_id=a.id AND p.status='active'
                 ORDER BY CASE WHEN p.id=s.selected_project_id THEN 0 ELSE 1 END,
                          CASE pm.role WHEN 'owner' THEN 0 WHEN 'editor' THEN 1 ELSE 2 END,
                          pm.created_at ASC,p.id
                 LIMIT 1
               ) selected ON true
               WHERE s.token_hash=%s AND s.expires_at>now()""",
            (token_hash,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE auth_sessions SET last_seen_at=now(),selected_project_id=%s WHERE token_hash=%s",
                (row.get("project_id"), token_hash),
            )
        else:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=%s OR expires_at<=now()", (token_hash,))
    return row


def account_projects(account_id: str) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """SELECT p.id,p.name,pm.role,p.default_locale,p.supported_locales
               FROM project_members pm JOIN projects p ON p.id=pm.project_id
               WHERE pm.account_id=%s AND p.status='active'
               ORDER BY pm.created_at,p.id""", (account_id,),
        ).fetchall()
    return {"projects": [{**row, "id": str(row["id"])} for row in rows]}


def select_project(token: str | None, account_id: str, project_id: str) -> None:
    try:
        target = uuid.UUID(project_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.") from exc
    with connection() as conn, conn.transaction():
        member = conn.execute(
            """SELECT p.id FROM project_members pm JOIN projects p ON p.id=pm.project_id
               WHERE pm.account_id=%s AND p.id=%s AND p.status='active'""",
            (account_id, target),
        ).fetchone()
        if not member:
            raise HTTPException(403, "이 계정에 배정된 프로젝트만 선택할 수 있습니다.")
        row = conn.execute(
            """UPDATE auth_sessions SET selected_project_id=%s,last_seen_at=now()
               WHERE token_hash=%s AND account_id=%s AND expires_at>now() RETURNING token_hash""",
            (target, hash_session_token(token or ""), account_id),
        ).fetchone()
        if not row:
            raise HTTPException(401, "로그인이 필요합니다.")


def create_session(account_id: uuid.UUID, request: Request) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "")
    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO auth_sessions(token_hash,account_id,expires_at,user_agent,ip_address)
               VALUES (%s,%s,%s,%s,%s)""",
            (hash_session_token(token), account_id, expires_at, request.headers.get("user-agent", "")[:500], client_ip[:100]),
        )
        conn.execute(
            "INSERT INTO login_events(account_id,ip_address,user_agent) VALUES (%s,%s,%s)",
            (account_id, client_ip[:100], request.headers.get("user-agent", "")[:500]),
        )
    return token, expires_at


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=AUTH_COOKIE_SECURE, httponly=True, samesite="lax")


def login(email: str, password: str) -> dict:
    try:
        normalized = normalize_login_identity(email)
    except ValueError:
        normalized = ""
    with connection() as conn:
        row = conn.execute(
            "SELECT id,password_hash FROM accounts WHERE lower(email)=lower(%s) AND is_active=true",
            (normalized,),
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    return row


def register_account(email: str, password: str, display_name: str) -> uuid.UUID:
    try:
        normalized = normalize_email(email)
        password = validate_password(password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    name = str(display_name or "").strip()
    if len(name) < 2 or len(name) > 80:
        raise HTTPException(422, "이름은 2~80자로 입력해 주세요.")
    account_id = uuid.uuid4()
    try:
        with connection() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO accounts(id,email,password_hash,display_name) VALUES (%s,%s,%s,%s)",
                (account_id, normalized, hash_password(password), name),
            )
    except UniqueViolation as exc:
        raise HTTPException(409, "이미 등록된 이메일입니다.") from exc
    return account_id


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with connection() as conn, conn.transaction():
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (hash_session_token(token),))
