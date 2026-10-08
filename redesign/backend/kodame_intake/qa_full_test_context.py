from __future__ import annotations

import argparse
import json
import re
import secrets
import uuid
from datetime import datetime

from psycopg.types.json import Jsonb

from .admin import MENU_KEYS
from .db import connection, open_pool, pool, tenant_context
from .report_sections import sync_report_sections
from .security import hash_password, normalize_email, validate_password


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,50}$")


def _default_run_id() -> str:
    return datetime.now().strftime("FT-%Y%m%d-%H%M%S")


def _password() -> str:
    return f"KODAME-FT-{secrets.token_urlsafe(9)}!"


def create_context(
    run_id: str,
    *,
    password: str | None = None,
    project_name: str | None = None,
) -> dict:
    run_id = str(run_id or "").strip()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id는 영문·숫자·점·밑줄·하이픈 3~51자로 입력하세요.")

    username = f"qa_{run_id.lower().replace('-', '_').replace('.', '_')}"
    email = normalize_email(f"{username}@kodame.local")
    password = validate_password(password or _password())
    project_name = str(project_name or f"[FULL TEST] 교통대 종료평가 {run_id}").strip()
    if not project_name or len(project_name) > 300:
        raise ValueError("프로젝트명은 1~300자로 입력하세요.")

    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    permissions = {key: True for key in MENU_KEYS}

    open_pool()
    with tenant_context(system=True):
        with connection() as conn, conn.transaction():
            if conn.execute("SELECT 1 FROM accounts WHERE lower(email)=lower(%s)", (email,)).fetchone():
                raise RuntimeError(f"이미 존재하는 풀테스트 계정입니다: {username}")
            if conn.execute("SELECT 1 FROM projects WHERE name=%s", (project_name,)).fetchone():
                raise RuntimeError(f"이미 존재하는 풀테스트 프로젝트입니다: {project_name}")
            conn.execute(
                """INSERT INTO accounts
                   (id,email,password_hash,display_name,is_active,is_admin,menu_permissions)
                   VALUES (%s,%s,%s,%s,true,false,%s)""",
                (
                    account_id,
                    email,
                    hash_password(password),
                    f"풀테스트 {run_id}",
                    Jsonb(permissions),
                ),
            )
            conn.execute(
                """INSERT INTO projects(id,owner_account_id,name,status,is_bootstrap)
                   VALUES (%s,%s,%s,'active',false)""",
                (project_id, account_id, project_name),
            )
            conn.execute(
                """INSERT INTO project_members(project_id,account_id,role)
                   VALUES (%s,%s,'owner')""",
                (project_id, account_id),
            )

    with tenant_context(project_id, account_id=account_id):
        sync_report_sections(force_bootstrap=False)
        with connection() as conn:
            section_count = conn.execute("SELECT count(*) AS count FROM report_sections").fetchone()["count"]

    return {
        "run_id": run_id,
        "account": {
            "username": username,
            "email": email,
            "password": password,
            "role": "owner",
        },
        "project": {
            "id": str(project_id),
            "name": project_name,
            "report_section_count": section_count,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an isolated K-ODAME full-test account and project.")
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--password")
    parser.add_argument("--project-name")
    args = parser.parse_args()
    try:
        print(json.dumps(
            create_context(args.run_id, password=args.password, project_name=args.project_name),
            ensure_ascii=False,
            indent=2,
        ))
    finally:
        if not pool.closed:
            pool.close()


if __name__ == "__main__":
    main()

