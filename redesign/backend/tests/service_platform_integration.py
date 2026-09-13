"""Explicit opt-in integration against a disposable database, NEVER production.

Run with KODAME_ISOLATED_TEST=1 and DB name kodame_service_isolated_test.
Uses local TestClient, real PostgreSQL/RLS, no LLM or renderer calls.
"""
import os
import uuid
from urllib.parse import urlparse

if os.getenv("KODAME_ISOLATED_TEST") != "1" or urlparse(os.environ.get("ADMIN_DATABASE_URL", "")).path != "/kodame_service_isolated_test":
    raise RuntimeError("This test must run only against the explicitly isolated disposable database.")

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from kodame_intake.main import app
from kodame_intake.db import connection, open_pool, tenant_context
from kodame_intake.project_lifecycle import capture_input_snapshot, recover_interrupted_sections
from kodame_intake.project_overview import generate_local_bootstrap_overview

checked = []


def check(condition, label):
    assert condition, label
    checked.append(label)
    print("PASS " + label, flush=True)


def request(client, method, path, expected=200, **kwargs):
    response = getattr(client, method)("/api/v2" + path, **kwargs)
    assert response.status_code == expected, (path, response.status_code, response.text)
    return response.json()


with TestClient(app) as operator:
    request(operator, "post", "/auth/login", json={"email": "admin", "password": os.environ["KODAME_BOOTSTRAP_PASSWORD"]})
    pa = request(operator, "post", "/admin/projects", 201, json={"name": "신규 사업 가", "supported_locales": ["ko"], "default_locale": "ko"})
    pb = request(operator, "post", "/admin/projects", 201, json={"name": "신규 사업 나", "supported_locales": ["ko"], "default_locale": "ko"})
    a = request(operator, "post", "/admin/accounts", 201, json={"username": "tenant_a", "password": "ClientPassword123!", "display_name": "고객 가", "project_id": pa["id"]})
    b = request(operator, "post", "/admin/accounts", 201, json={"username": "tenant_b", "password": "ClientPassword123!", "display_name": "고객 나", "project_id": pb["id"]})
    check(a["project"]["id"] == pa["id"] and b["project"]["id"] == pb["id"], "project-first issuance links only the selected project")
    request(operator, "get", "/dashboard", 403)
    check(True, "operator cannot access client analysis workspace")
    client_a, client_b = TestClient(app), TestClient(app)
    request(client_a, "post", "/auth/login", json={"email": "tenant_a", "password": "ClientPassword123!"})
    request(client_b, "post", "/auth/login", json={"email": "tenant_b", "password": "ClientPassword123!"})
    blank = request(client_a, "get", "/dashboard")
    check(blank["document_count"] == 0 and blank["is_empty"] and blank["project"]["country"] == "" and blank["project"]["budget"] == "", "empty dashboard contains no sample country/budget")
    check(request(client_a, "get", "/project-overview")["overview"] is None, "empty project overview has no sample facts")
    sections = request(client_a, "get", "/report/sections")["items"]
    check(len(sections) == 27 and all(not s["content"] and s["status"] == "empty" for s in sections), "27 independently defined sections begin truly empty")
    request(client_a, "put", "/account/projects/" + pb["id"] + "/select", 403)
    check(True, "unassigned project selection denied")
    # Upload through the actual HTTP path; no worker/AI is started.
    upload = request(client_a, "post", "/intake/uploads", 202, files={"files": ("tenant-a-only.txt", b"Only tenant A input.", "text/plain")})
    with tenant_context(pa["id"]), connection() as conn:
        doc = conn.execute("SELECT id FROM intake_documents").fetchone()
    check(doc is not None, "public upload stores document in selected tenant")
    request(client_a, "post", "/evaluations", 409)
    check(True, "evaluation is blocked while uploaded documents are still processing")
    request(client_b, "get", "/intake/jobs/" + str(doc["id"]), 404)
    check(request(client_b, "get", "/dashboard")["document_count"] == 0, "real PostgreSQL RLS hides other tenant document and statistics")
    menus = {key: True for key in a["menu_permissions"]}
    menus["evaluation_report"] = False
    request(operator, "put", "/admin/accounts/" + a["id"] + "/menus", json={"menu_permissions": menus})
    request(client_a, "get", "/report/sections", 403)
    menus["evaluation_report"] = True
    request(operator, "put", "/admin/accounts/" + a["id"] + "/menus", json={"menu_permissions": menus})
    request(client_a, "get", "/report/sections")
    check(True, "administrator menu setting applies immediately to viewer account")
    menus["evidence_upload"] = False
    request(operator, "put", "/admin/accounts/" + a["id"] + "/menus", json={"menu_permissions": menus})
    request(client_a, "post", "/intake/uploads", 403, files={"files": ("denied.txt", b"Must not be stored.", "text/plain")})
    menus["evidence_upload"] = True
    request(operator, "put", "/admin/accounts/" + a["id"] + "/menus", json={"menu_permissions": menus})
    check(True, "upload menu denial is enforced by backend before any file is written")
    request(operator, "put", "/admin/projects/" + pb["id"] + "/members/" + a["id"])
    request(client_a, "put", "/account/projects/" + pa["id"] + "/select")
    with tenant_context(system=True), connection() as conn, conn.transaction():
        conn.execute("UPDATE projects SET updated_at=now() WHERE id=%s", (pb["id"],))
    check(request(client_a, "get", "/auth/me")["project"]["id"] == pa["id"], "selected project remains stable when another project changes")
    check(len(request(client_a, "get", "/account/projects")["projects"]) == 2, "account can list assigned projects explicitly")
    request(client_a, "put", "/account/projects/" + pb["id"] + "/select")
    check(request(client_a, "get", "/dashboard")["document_count"] == 0, "switching project changes RLS data boundary")
    request(operator, "delete", "/admin/projects/" + pb["id"] + "/members/" + a["id"])
    check(request(client_a, "get", "/auth/me")["project"]["id"] == pa["id"], "removing membership revokes selected project on next request")
    with tenant_context(pa["id"]), connection() as conn, conn.transaction():
        conn.execute("UPDATE intake_documents SET status='completed',completed_at=now(),updated_at=now()")
        snapshot = capture_input_snapshot(conn)
        run_id = uuid.uuid4()
        conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count,completed_at,input_snapshot) VALUES (%s,'completed','isolated-test',1,now(),%s)", (run_id, Jsonb(snapshot)))
        snapshot = capture_input_snapshot(conn)
        conn.execute("UPDATE report_sections SET content='현재 자료 기반 시험 본문',status='draft',generated_at=now(),generation_metadata=%s", (Jsonb({"input_snapshot": snapshot}),))
    check(request(client_a, "get", "/project/lifecycle")["report_current"], "completed evaluation and matching report revision are current")
    request(client_a, "post", "/intake/uploads", 202, files={"files": ("new-evidence.txt", b"New evidence.", "text/plain")})
    check(request(client_a, "get", "/project/lifecycle")["phase"] == "processing_documents", "new input invalidates latest-data claim immediately")
    with tenant_context(pa["id"]), connection() as conn, conn.transaction():
        conn.execute("UPDATE intake_documents SET status='completed',completed_at=now(),updated_at=now() WHERE status<>'completed'")
    check(request(client_a, "get", "/project/lifecycle")["phase"] == "evaluation_required", "completed new data requires reevaluation before generation")
    request(client_a, "post", "/report/generate-all", 409)
    request(client_a, "post", "/report/sections/summary-ko/generate", 409, json={"instruction": "수정"})
    check(True, "stale data cannot silently generate a supposedly current report")
    with tenant_context(pa["id"]), connection() as conn, conn.transaction():
        snapshot = capture_input_snapshot(conn)
        conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count,completed_at,input_snapshot) VALUES (%s,'completed','isolated-test',2,now(),%s)", (uuid.uuid4(), Jsonb(snapshot)))
    state = request(client_a, "get", "/project/lifecycle")
    check(state["evaluation_current"] and len(state["stale_section_ids"]) == 27, "reevaluation preserves and marks previous 27 drafts stale")
    with tenant_context(pa["id"]), connection() as conn, conn.transaction():
        conn.execute("UPDATE report_sections SET status='generating' WHERE part_id='summary-ko'")
        check(recover_interrupted_sections(conn) == 1, "orphaned single-section job recovered")
        restored = conn.execute("SELECT content,status FROM report_sections WHERE part_id='summary-ko'").fetchone()
        check(restored["content"] and restored["status"] == "draft", "recovery preserves previous draft content")
    request(operator, "put", "/admin/accounts/" + a["id"] + "/password", json={"password": "ChangedPassword456!"})
    request(client_a, "get", "/auth/me", 401)
    request(client_a, "post", "/auth/login", json={"email": "tenant_a", "password": "ChangedPassword456!"})
    request(operator, "put", "/admin/accounts/" + b["id"] + "/status", json={"is_active": False})
    request(client_b, "get", "/auth/me", 401)
    open_pool()  # Same startup initializer used by worker/evaluation, no restart.
    request(client_a, "post", "/auth/login", json={"email": "tenant_a", "password": "ChangedPassword456!"})
    request(client_b, "post", "/auth/login", 401, json={"email": "tenant_b", "password": "ClientPassword123!"})
    check(True, "credential resets and suspended accounts survive bootstrap initializer")
    accounts = request(operator, "get", "/admin/accounts")["accounts"]
    check(len(accounts) == 3 and not any(a["username"].startswith("test") for a in accounts), "no ten demo accounts are silently seeded")
    try:
        generate_local_bootstrap_overview()
    except RuntimeError:
        check(True, "legacy sample overview injection explicitly disabled")
    else:
        raise AssertionError("legacy sample injection unexpectedly enabled")
print(f"ISOLATED_SERVICE_INTEGRATION_PASSED {len(checked)} checks", flush=True)
