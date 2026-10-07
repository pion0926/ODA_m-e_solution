"""Data revision contract for upload -> evaluation -> report -> repeat.

Snapshots never replace content. They distinguish historical, usable drafts from
an artifact proven to reflect the current project data. No sample facts enter here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .db import connection, current_project_id


# Terminal failures of optional uploads do not lock the whole project.
DOCUMENT_BLOCKS_WORKFLOW_SQL = "(status NOT IN ('completed','failed','cancelled') OR (upload_role<>'evidence' AND status<>'completed'))"


def document_blocks_workflow(row):
    if row.get('evaluation_excluded'):
        return False
    return row['status'] != 'completed' and (
        row['status'] not in ('failed', 'cancelled') or row.get('upload_role', 'evidence') != 'evidence')


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _time(value):
    if not value:
        return None
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if not isinstance(value, datetime) else value
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def input_snapshot_from_rows(documents: list[dict], evaluation: dict | None = None) -> dict:
    """Order-independent fingerprint; includes same-count replacement/reanalysis."""
    rows = sorted(({
        "id": str(row["id"]), "sha256": str(row.get("sha256") or ""),
        "status": row.get("status"), "updated_at": _iso(row.get("updated_at")),
    } for row in documents), key=lambda row: row["id"])
    changes = [_time(row.get("updated_at")) for row in documents if row.get("updated_at")]
    return {
        "version": 1,
        "document_count": len(rows),
        "completed_document_count": sum(row["status"] == "completed" for row in rows),
        "failed_document_count": sum(row["status"] == "failed" for row in rows),
        "pending_document_count": sum(document_blocks_workflow(row) for row in documents),
        "cancelled_document_count": sum(row["status"] == "cancelled" for row in rows),
        "waiting_document_count": sum(row["status"] == "waiting_llm" for row in rows),
        "document_digest": hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "latest_document_change": _iso(max(changes)) if changes else None,
        "evaluation_run_id": str(evaluation["id"]) if evaluation else None,
        "evaluation_completed_at": _iso(evaluation.get("completed_at")) if evaluation else None,
    }


def capture_input_snapshot(conn=None) -> dict:
    if conn is None:
        with connection() as current:
            return capture_input_snapshot(current)
    documents = conn.execute("SELECT id,sha256,status,updated_at,upload_role FROM evaluation_intake_documents ORDER BY id").fetchall()
    evaluation = conn.execute(
        "SELECT id,completed_at FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    from .evaluation_versions import project_inputs, digest
    return {**input_snapshot_from_rows(documents, evaluation),
            'workflow_digest': digest(project_inputs(conn))}


def snapshots_match(before: dict | None, after: dict | None, *, include_evaluation: bool = True) -> bool:
    if not before or not after or not before.get("document_digest") or not after.get("document_digest"):
        return False
    return before["document_digest"] == after["document_digest"] and (
        before.get('workflow_digest') == after.get('workflow_digest')) and (
        not include_evaluation or before.get("evaluation_run_id") == after.get("evaluation_run_id")
    )


def evaluate_freshness(snapshot: dict, evaluation: dict | None, sections: list[dict], *, active_evaluation: bool = False) -> dict:
    total = int(snapshot["document_count"])
    completed = int(snapshot["completed_document_count"])
    pending = int(snapshot.get('pending_document_count', total - completed - int(snapshot.get('failed_document_count', 0)) - int(snapshot.get('cancelled_document_count', 0))))
    failed = int(snapshot.get("failed_document_count", 0))
    waiting = int(snapshot.get("waiting_document_count", 0))
    evaluation_current = False
    if evaluation and evaluation.get("status") == "completed" and not pending and completed:
        source = evaluation.get("input_snapshot") or {}
        if source.get("document_digest"):
            evaluation_current = snapshots_match(source, snapshot, include_evaluation=False)
        else:
            # Upgrade path for existing reports: conservative timestamp/count
            # check against evaluation START, not completion (uploads can race).
            changed, started = _time(snapshot.get("latest_document_change")), _time(evaluation.get("started_at"))
            evaluation_current = int(evaluation.get("document_count") or 0) == completed and bool(started) and (not changed or changed <= started)
    stale = []
    missing = []
    active = []
    for section in sections:
        part_id = section["part_id"]
        if section.get("status") == "generating":
            active.append(part_id)
        if not str(section.get("content") or "").strip():
            missing.append(part_id)
            continue
        saved = (section.get("generation_metadata") or {}).get("input_snapshot") or {}
        if saved.get("document_digest"):
            current = evaluation_current and snapshots_match(saved, snapshot)
        else:
            generated = _time(section.get("generated_at")) or _time(section.get("updated_at"))
            evaluated = _time(snapshot.get("evaluation_completed_at"))
            current = evaluation_current and bool(generated and evaluated and generated >= evaluated)
        if not current:
            stale.append(part_id)
    if not total:
        phase, message = "empty_project", "자료를 업로드해 주세요."
    elif waiting or (not completed and failed):
        phase, message = "documents_need_attention", f"문서 분석 실패 {failed}건 · AI 연결 대기 {waiting}건이 있습니다. 자료 업로드 화면에서 원인을 확인하고 재시도해 주세요."
    elif pending:
        phase, message = "processing_documents", f"문서 {pending}건 분석이 완료되면 재평가할 수 있습니다."
    elif active_evaluation:
        phase, message = "evaluation_active", "DAC 질문별 증빙을 평가하고 있습니다. 입력이 같은 완료 질문은 재사용합니다. 완료 후 보고서를 생성해 주세요."
    elif not evaluation_current:
        phase, message = "evaluation_required", "현재 자료를 반영하려면 DAC 평가진단을 실행해 주세요. 변경된 질문을 재검토하며 기존 결과는 보존됩니다."
    elif active:
        phase, message = "report_generating", "보고서를 생성하고 있습니다."
    elif not sections or missing or stale:
        phase, message = "report_required", "최신 평가에 맞춰 보고서를 생성해 주세요. 기존 초안은 보존됩니다."
    else:
        phase, message = "current", "현재 자료와 평가를 반영한 보고서입니다."
    return {
        "phase": phase, "message": message, "input_snapshot": snapshot,
        "evaluation_current": evaluation_current, "evaluation_stale": bool(evaluation and not evaluation_current),
        "evaluation_active": active_evaluation,
        "can_evaluate": bool(completed and not pending and not active_evaluation),
        "can_generate_report": evaluation_current and not active and not active_evaluation,
        "report_current": evaluation_current and bool(sections) and not (missing or stale or active or active_evaluation),
        "stale_section_ids": stale, "missing_section_ids": missing, "active_section_ids": active,
        "pending_document_count": pending,
        "excluded_document_count": total - completed - pending,
        "failed_document_count": failed, "waiting_document_count": waiting,
    }


def project_lifecycle(conn=None) -> dict:
    if conn is None:
        with connection() as current:
            return project_lifecycle(current)
    snapshot = capture_input_snapshot(conn)
    evaluation = conn.execute(
        "SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    sections = conn.execute(
        "SELECT part_id,status,content,generation_metadata,generated_at,updated_at FROM report_sections ORDER BY section_number"
    ).fetchall()
    active_evaluation = conn.execute("SELECT id FROM evaluation_runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
    return evaluate_freshness(snapshot, evaluation, sections, active_evaluation=bool(active_evaluation))


def lock_project_workflow(conn) -> None:
    """Serialize job-start transactions per tenant, not across customers."""
    project_id = current_project_id()
    if not project_id:
        raise RuntimeError("프로젝트가 선택되지 않았습니다.")
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"kodame:workflow:{project_id}",))


def active_workflow_jobs(conn) -> list[str]:
    rows = conn.execute(
        """SELECT 'evaluation' AS kind FROM evaluation_runs WHERE status IN ('queued','running')
           UNION ALL SELECT 'pdm_refresh' FROM pdm_refresh_runs WHERE status IN ('queued','running')
           UNION ALL SELECT 'report_generation' FROM report_generation_runs WHERE status IN ('queued','running')
           UNION ALL SELECT 'section_generation' FROM report_sections WHERE status='generating'
           UNION ALL SELECT 'report_export' FROM report_exports WHERE status IN ('queued','running')
           UNION ALL SELECT 'presentation_export' FROM presentation_exports WHERE status IN ('queued','running')
           UNION ALL SELECT 'translation' FROM translation_jobs WHERE status IN ('queued','running')"""
    ).fetchall()
    return sorted({row["kind"] for row in rows})


def recover_interrupted_sections(conn) -> int:
    """Preserve prior drafts; only release orphaned per-section execution locks."""
    result = conn.execute(
        """UPDATE report_sections SET
             status=CASE WHEN btrim(content)<>'' THEN 'draft' ELSE 'empty' END,
             error_message='서버 재시작으로 AI 생성이 중단되었습니다. 기존 내용은 보존되었으며 다시 생성할 수 있습니다.',
             generation_metadata=generation_metadata || '{"interrupted":true}'::jsonb,
             updated_at=now() WHERE status='generating'"""
    )
    return result.rowcount
