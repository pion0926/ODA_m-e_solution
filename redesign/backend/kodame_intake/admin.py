from __future__ import annotations

import uuid

from fastapi import HTTPException
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from .db import connection, tenant_context
from .translations import LANGUAGES, normalize_locales, translation_seed
from .security import hash_password, normalize_login_identity, validate_password


MENU_KEYS = (
    "dashboard", "evidence_upload", "evidence_pdm", "evidence_dac",
    "evidence_coverage", "project_overview", "project_indicators",
    "project_gaps", "evaluation_overview", "evaluation_board",
    "evaluation_results", "evaluation_report",
)


def require_admin(session: dict | None) -> None:
    if not session or not session.get("is_admin"):
        raise HTTPException(403, "관리자 계정만 접근할 수 있습니다.")


def has_menu_permission(session: dict | None, menu_key: str) -> bool:
    """Return the effective permission configured in the admin console.

    Existing accounts predate menu permissions, so an omitted key remains allowed.
    An explicit ``false`` denies access. Operators use only the admin console;
    project work requires a separately issued service account.
    """
    if not session or menu_key not in MENU_KEYS:
        return False
    if session.get("is_admin"):
        return False
    return (session.get("menu_permissions") or {}).get(menu_key, True) is not False


def mutation_menu_permission(method: str, path: str) -> str | None:
    """Menus are enforced on expensive/data-changing APIs, not just navigation."""
    if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if path.startswith("/api/v2/report/"):
        return "evaluation_report"
    if path == "/api/v2/intake/uploads" or (path.startswith("/api/v2/intake/jobs/") and path.endswith(("/retry", "/cancel", "/mode", "/evaluation-scope"))):
        return "evidence_upload"
    if path == "/api/v2/evaluations":
        return "evaluation_board"
    if path == "/api/v2/pdm/refresh":
        return "project_indicators"
    if path.startswith("/api/v2/intake/suggestions/"):
        return "evidence_coverage"
    return None


def list_accounts() -> dict:
    with tenant_context(system=True):
        with connection() as conn:
            rows = conn.execute(
                """SELECT a.id,a.email,a.display_name,a.is_admin,a.is_active,a.menu_permissions,a.created_at,
                          p.id AS project_id,p.name AS project_name,p.role,
                          COALESCE(u.prompt_tokens,0) AS prompt_tokens,
                          COALESCE(u.completion_tokens,0) AS completion_tokens,
                          COALESCE(u.total_tokens,0) AS total_tokens,
                          l.logged_in_at AS last_login_at,l.ip_address AS last_login_ip
                   FROM accounts a
                   LEFT JOIN LATERAL (
                     SELECT p.id,p.name,pm.role FROM project_members pm
                     JOIN projects p ON p.id=pm.project_id
                     WHERE pm.account_id=a.id AND p.status='active'
                     ORDER BY p.updated_at DESC LIMIT 1
                   ) p ON true
                   LEFT JOIN LATERAL (
                     SELECT sum(prompt_tokens) prompt_tokens,sum(completion_tokens) completion_tokens,sum(total_tokens) total_tokens
                     FROM token_usage_events WHERE account_id=a.id
                   ) u ON true
                   LEFT JOIN LATERAL (
                     SELECT logged_in_at,ip_address FROM login_events WHERE account_id=a.id
                     ORDER BY logged_in_at DESC LIMIT 1
                   ) l ON true
                   ORDER BY a.is_admin DESC,a.email"""
            ).fetchall()
            memberships = conn.execute(
                """SELECT pm.account_id,p.id,p.name,pm.role FROM project_members pm
                   JOIN projects p ON p.id=pm.project_id WHERE p.status='active'
                   ORDER BY pm.created_at,p.id"""
            ).fetchall()
    projects_by_account: dict[str, list[dict]] = {}
    for member in memberships:
        projects_by_account.setdefault(str(member["account_id"]), []).append(
            {"id": str(member["id"]), "name": member["name"], "role": member["role"]})
    accounts = []
    for row in rows:
        permissions = {key: True for key in MENU_KEYS}
        permissions.update(row.get("menu_permissions") or {})
        accounts.append({
            "id": str(row["id"]), "username": row["email"].split("@", 1)[0],
            "email": row["email"], "display_name": row["display_name"],
            "is_admin": row["is_admin"], "is_active": row["is_active"],
            "project": ({"id": str(row["project_id"]), "name": row["project_name"], "role": row["role"]} if row.get("project_id") else None),
            "projects": projects_by_account.get(str(row["id"]), []),
            "menu_permissions": permissions,
            "usage": {"prompt_tokens": row["prompt_tokens"], "completion_tokens": row["completion_tokens"], "total_tokens": row["total_tokens"]},
            "last_login_at": row["last_login_at"].isoformat() if row.get("last_login_at") else None,
            "last_login_ip": row.get("last_login_ip") or "-",
            "created_at": row["created_at"].isoformat(),
        })
    return {"accounts": accounts, "menu_keys": list(MENU_KEYS)}


def list_projects() -> dict:
    from .project_ai import policy_payload
    with tenant_context(system=True):
        with connection() as conn:
            rows = conn.execute(
                """SELECT p.id,p.name,p.status,p.default_locale,p.supported_locales,p.created_at,
                          p.llm_model,p.ai_revision,p.ai_updated_at,
                          count(pm.account_id) FILTER (WHERE NOT a.is_admin) AS member_count,
                          (SELECT count(*) FROM intake_documents d WHERE d.project_id=p.id) AS document_count,
                          (SELECT count(*) FROM evaluation_runs e WHERE e.project_id=p.id AND e.status='completed') AS evaluation_count,
                          (SELECT count(*) FROM report_sections r WHERE r.project_id=p.id AND length(trim(r.content))>0) AS written_sections
                   FROM projects p LEFT JOIN project_members pm ON pm.project_id=p.id
                   LEFT JOIN accounts a ON a.id=pm.account_id
                   GROUP BY p.id ORDER BY p.created_at DESC"""
            ).fetchall()
    return {
        "projects": [{
            **policy_payload(row),
            "id": str(row["id"]), "name": row["name"], "status": row["status"],
            "default_locale": row["default_locale"], "supported_locales": row["supported_locales"],
            "member_count": row["member_count"], "created_at": row["created_at"].isoformat(),
            "document_count": row["document_count"], "evaluation_count": row["evaluation_count"], "written_sections": row["written_sections"],
        } for row in rows],
        "languages": LANGUAGES,
    }


def create_project(owner_account_id: str, name: str, supported_locales: list[str], default_locale: str, account_ids: list[str]) -> dict:
    from .llm_models import DEFAULT_MODEL
    try:
        owner_id = uuid.UUID(str(owner_account_id))
        member_ids = list(dict.fromkeys(uuid.UUID(str(value)) for value in account_ids))
    except ValueError as exc:
        raise HTTPException(422, "배정할 계정 정보가 올바르지 않습니다.") from exc
    try:
        locales, default = normalize_locales(supported_locales, default_locale)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    clean_name = str(name or "").strip()
    if len(clean_name) < 2:
        raise HTTPException(422, "프로젝트명을 2자 이상 입력해 주세요.")
    project_id = uuid.uuid4()
    with tenant_context(system=True):
        with connection() as conn, conn.transaction():
            if not conn.execute("SELECT id FROM accounts WHERE id=%s AND is_active=true", (owner_id,)).fetchone():
                raise HTTPException(422, "프로젝트 소유자 계정을 확인해 주세요.")
            existing_ids = {row["id"] for row in conn.execute("SELECT id FROM accounts WHERE id=ANY(%s) AND is_active=true ORDER BY id FOR UPDATE", (member_ids,)).fetchall()} if member_ids else set()
            if len(existing_ids) != len(member_ids):
                raise HTTPException(422, "존재하지 않거나 비활성화된 계정이 포함되어 있습니다.")
            conn.execute(
                """INSERT INTO projects(id,owner_account_id,name,default_locale,supported_locales,llm_model)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (project_id, owner_id, clean_name, default, locales, DEFAULT_MODEL),
            )
            # The operator owns administration, not membership in the client's data workspace.
            for account_id in existing_ids - {owner_id}:
                conn.execute(
                    "INSERT INTO project_members(project_id,account_id,role,preferred_locale) VALUES (%s,%s,'viewer',%s)",
                    (project_id, account_id, default),
                )
            for locale in locales:
                conn.execute(
                    "INSERT INTO project_translations(project_id,locale,translations) VALUES (%s,%s,%s)",
                    (project_id, locale, Jsonb(translation_seed(locale))),
                )
    return {
        "id": str(project_id), "name": clean_name, "status": "active",
        "default_locale": default, "supported_locales": locales,
        "member_count": len(existing_ids - {owner_id}),
    }


def update_menu_permissions(account_id: str, permissions: dict) -> dict:
    try:
        target_id = uuid.UUID(account_id)
    except ValueError as exc:
        raise HTTPException(404, "계정을 찾을 수 없습니다.") from exc
    normalized = {key: bool(permissions.get(key, False)) for key in MENU_KEYS}
    with tenant_context(system=True):
        with connection() as conn, conn.transaction():
            row = conn.execute("SELECT is_admin FROM accounts WHERE id=%s", (target_id,)).fetchone()
            if not row:
                raise HTTPException(404, "계정을 찾을 수 없습니다.")
            if row["is_admin"]:
                raise HTTPException(422, "관리자 메뉴 권한은 변경할 수 없습니다.")
            conn.execute(
                "UPDATE accounts SET menu_permissions=%s,updated_at=now() WHERE id=%s",
                (Jsonb(normalized), target_id),
            )
    return {"id": str(target_id), "menu_permissions": normalized}


def login_history(account_id: str, limit: int = 20) -> dict:
    try:
        target_id = uuid.UUID(account_id)
    except ValueError as exc:
        raise HTTPException(404, "계정을 찾을 수 없습니다.") from exc
    with tenant_context(system=True):
        with connection() as conn:
            rows = conn.execute(
                """SELECT logged_in_at,ip_address,user_agent FROM login_events
                   WHERE account_id=%s ORDER BY logged_in_at DESC LIMIT %s""",
                (target_id, max(1, min(limit, 100))),
            ).fetchall()
    return {"items": [{"logged_in_at": row["logged_in_at"].isoformat(), "ip_address": row.get("ip_address") or "-", "user_agent": row.get("user_agent") or "-"} for row in rows]}


def _account_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise HTTPException(404, "계정 또는 프로젝트를 찾을 수 없습니다.") from exc


def create_account(username: str, password: str, display_name: str, permissions: dict | None = None, project_id: str | None = None) -> dict:
    """Issue a service account and initial membership in one transaction."""
    try:
        email = normalize_login_identity(username)
        clean_password = validate_password(password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    name = str(display_name or "").strip()
    if not 2 <= len(name) <= 80:
        raise HTTPException(422, "이름은 2~80자로 입력해 주세요.")
    target_id = uuid.uuid4()
    configured = {key: bool((permissions or {}).get(key, True)) for key in MENU_KEYS}
    project = _account_uuid(project_id) if project_id else None
    project_row = None
    try:
        with tenant_context(system=True), connection() as conn, conn.transaction():
            if project:
                project_row = conn.execute("SELECT id,name,default_locale FROM projects WHERE id=%s AND status='active' FOR UPDATE", (project,)).fetchone()
                if not project_row:
                    raise HTTPException(422, "활성 프로젝트를 선택해 주세요. 계정은 발급되지 않았습니다.")
            conn.execute(
                """INSERT INTO accounts(id,email,password_hash,display_name,menu_permissions)
                   VALUES (%s,%s,%s,%s,%s)""",
                (target_id, email, hash_password(clean_password), name, Jsonb(configured)),
            )
            if project_row:
                conn.execute("INSERT INTO project_members(project_id,account_id,role,preferred_locale) VALUES (%s,%s,'editor',%s)",
                             (project, target_id, project_row["default_locale"]))
    except UniqueViolation as exc:
        raise HTTPException(409, "이미 발급된 아이디입니다.") from exc
    return {"id": str(target_id), "username": email.split("@", 1)[0], "email": email,
            "display_name": name, "is_active": True, "is_admin": False,
            "project": {"id": str(project), "name": project_row["name"], "role": "editor"} if project_row else None,
            "menu_permissions": configured}


def update_account_status(account_id: str, active: bool) -> dict:
    target_id = _account_uuid(account_id)
    with tenant_context(system=True), connection() as conn, conn.transaction():
        row = conn.execute("SELECT is_admin FROM accounts WHERE id=%s FOR UPDATE", (target_id,)).fetchone()
        if not row:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        if row["is_admin"]:
            raise HTTPException(422, "관리자 계정은 이 화면에서 비활성화할 수 없습니다.")
        conn.execute("UPDATE accounts SET is_active=%s,updated_at=now() WHERE id=%s", (active, target_id))
        if not active:
            conn.execute("DELETE FROM auth_sessions WHERE account_id=%s", (target_id,))
    return {"id": str(target_id), "is_active": active}


def reset_account_password(account_id: str, password: str) -> dict:
    target_id = _account_uuid(account_id)
    try:
        encoded = hash_password(password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with tenant_context(system=True), connection() as conn, conn.transaction():
        row = conn.execute(
            "UPDATE accounts SET password_hash=%s,updated_at=now() WHERE id=%s RETURNING id", (encoded, target_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        conn.execute("DELETE FROM auth_sessions WHERE account_id=%s", (target_id,))
    return {"id": str(target_id), "sessions_revoked": True}


def assign_project_member(project_id: str, account_id: str, *, remove: bool = False) -> dict:
    project = _account_uuid(project_id)
    target = _account_uuid(account_id)
    with tenant_context(system=True), connection() as conn, conn.transaction():
        account = conn.execute("SELECT id,is_active,is_admin FROM accounts WHERE id=%s FOR UPDATE", (target,)).fetchone()
        if not account or account["is_admin"] or (not remove and not account["is_active"]):
            raise HTTPException(422, "활성 사용자 계정만 프로젝트에 배정할 수 있습니다.")
        project_row = conn.execute("SELECT owner_account_id,default_locale FROM projects WHERE id=%s AND status='active' FOR UPDATE", (project,)).fetchone()
        if not project_row:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        if target == project_row["owner_account_id"]:
            raise HTTPException(422, "프로젝트 소유자 배정은 변경할 수 없습니다.")
        if remove:
            conn.execute("DELETE FROM project_members WHERE project_id=%s AND account_id=%s", (project, target))
            conn.execute("UPDATE auth_sessions SET selected_project_id=NULL WHERE account_id=%s AND selected_project_id=%s", (target, project))
        else:
            conn.execute(
                """INSERT INTO project_members(project_id,account_id,role,preferred_locale)
                   VALUES (%s,%s,'viewer',%s) ON CONFLICT(project_id,account_id) DO NOTHING""",
                (project, target, project_row["default_locale"]),
            )
    return {"project_id": str(project), "account_id": str(target), "assigned": not remove}


def replace_project_memberships(account_id: str, project_ids: list[str], expected_project_ids: list[str]) -> dict:
    """Validate the entire change before writing; serialize all account membership writers."""
    target = _account_uuid(account_id)
    desired = {_account_uuid(value) for value in project_ids}
    expected = {_account_uuid(value) for value in expected_project_ids}
    with tenant_context(system=True), connection() as conn, conn.transaction():
        account = conn.execute("SELECT is_active,is_admin FROM accounts WHERE id=%s FOR UPDATE", (target,)).fetchone()
        if not account:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        if account["is_admin"]:
            raise HTTPException(422, "관리자는 사용자 프로젝트 배정 대상이 아닙니다.")
        current = {row["id"] for row in conn.execute(
            """SELECT p.id FROM project_members pm JOIN projects p ON p.id=pm.project_id
               WHERE pm.account_id=%s AND p.status='active'""", (target,)).fetchall()}
        if current != expected:
            raise HTTPException(409, "다른 관리자가 프로젝트 배정을 변경했습니다. 최신 목록을 확인한 후 다시 저장해 주세요.")
        added, removed = desired - current, current - desired
        if added and not account["is_active"]:
            raise HTTPException(422, "중지된 계정은 활성화한 후 새 프로젝트에 배정해 주세요.")
        projects = conn.execute(
            "SELECT id,owner_account_id,default_locale FROM projects WHERE id=ANY(%s) AND status='active' ORDER BY id FOR UPDATE",
            (sorted(desired | removed),),
        ).fetchall()
        if {row["id"] for row in projects} != desired | removed:
            raise HTTPException(422, "존재하지 않거나 종료된 프로젝트가 포함되어 있습니다. 배정은 변경되지 않았습니다.")
        if any(row["owner_account_id"] == target and row["id"] in added | removed for row in projects):
            raise HTTPException(422, "프로젝트 소유자 배정은 변경할 수 없습니다.")
        for row in projects:
            if row["id"] in added:
                conn.execute("INSERT INTO project_members(project_id,account_id,role,preferred_locale) VALUES (%s,%s,'viewer',%s)",
                             (row["id"], target, row["default_locale"]))
        if removed:
            conn.execute("DELETE FROM project_members WHERE account_id=%s AND project_id=ANY(%s)", (target, sorted(removed)))
            conn.execute("UPDATE auth_sessions SET selected_project_id=NULL WHERE account_id=%s AND selected_project_id=ANY(%s)",
                         (target, sorted(removed)))
    return {"account_id": str(target), "project_ids": sorted(map(str, desired)), "added_count": len(added), "removed_count": len(removed)}
