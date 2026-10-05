"""Administrator-owned project policy. Requests/jobs use an immutable snapshot."""
from fastapi import HTTPException

from .db import connection, current_project_id, tenant_context
from .llm_models import DEFAULT_MODEL, validate_model
from .model_catalog import require_available_model


def policy_payload(row: dict) -> dict:
    return {"llm_model": row.get("llm_model") or DEFAULT_MODEL,
            "ai_revision": row.get("ai_revision", 0),
            "ai_updated_at": row["ai_updated_at"].isoformat() if row.get("ai_updated_at") else None}


def get_project_model(project_id=None) -> str:
    project_id = project_id or current_project_id()
    if not project_id:
        raise HTTPException(403, "AI 작업에 사용할 프로젝트가 배정되지 않았습니다.")
    with connection() as conn:
        row = conn.execute("SELECT llm_model FROM projects WHERE id=%s AND status='active'", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "활성 프로젝트를 찾을 수 없습니다.")
    # Invalid persisted values must not silently route to a different model.
    try:
        return validate_model(row.get("llm_model") or DEFAULT_MODEL)
    except ValueError as exc:
        raise HTTPException(409, "프로젝트 AI 모델을 관리자가 다시 배정해야 합니다.") from exc


def update_project_model(project_id, model, expected_revision, actor_id) -> dict:
    try:
        selected = require_available_model(model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with tenant_context(system=True), connection() as conn, conn.transaction():
        row = conn.execute("SELECT * FROM projects WHERE id=%s FOR UPDATE", (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        if row["status"] != "active":
            raise HTTPException(409, "활성 프로젝트에만 모델을 배정할 수 있습니다.")
        if row["ai_revision"] != expected_revision:
            raise HTTPException(409, "다른 관리자가 설정을 변경했습니다. 새로고침 후 다시 확인해 주세요.")
        previous = row.get("llm_model") or DEFAULT_MODEL
        if previous != selected:
            row = conn.execute(
                """UPDATE projects SET llm_model=%s,ai_revision=ai_revision+1,
                   ai_updated_at=now(),updated_at=now() WHERE id=%s RETURNING *""",
                (selected, project_id)).fetchone()
            conn.execute(
                """INSERT INTO project_ai_changes(project_id,account_id,previous_model,selected_model,revision)
                   VALUES (%s,%s,%s,%s,%s)""", (project_id, actor_id, previous, selected, row["ai_revision"]))
    return {"project_id": str(project_id), **policy_payload(row),
            "message": "다음 AI 작업부터 적용됩니다. 진행 중인 작업과 저장된 분석·보고서는 유지됩니다."}
