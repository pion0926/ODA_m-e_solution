from __future__ import annotations

import os
import socket
import time
import traceback
from datetime import timedelta
from pathlib import Path
from threading import Lock

from psycopg.types.json import Jsonb

from .db import connection, open_pool, tenant_context
from .document_slots import document_slot_matches
from .llm_models import llm_model_context
from .openrouter import AnalysisError, MissingApiKey, analyze_document
from .parsers import ParseError, parse_document
from .pdm_monitoring import refresh_pdm_model
from .project_overview import generate_project_overview, overview_source_document_count
from .settings import EXTRACTED_DIR, MAX_ATTEMPTS, TAXONOMY_VERSION, WORKER_POLL_SECONDS, WORKER_STEP_DELAY_SECONDS

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_OVERVIEW_REFRESH_LOCK = Lock()


def refresh_project_overview_if_needed() -> None:
    """Create an early overview and refresh it when all authoritative inputs finish."""
    if not _OVERVIEW_REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        source_count = overview_source_document_count()
        if not source_count:
            return
        with connection() as conn:
            latest = conn.execute(
                "SELECT document_count FROM project_overviews ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            pending_authoritative = conn.execute(
                """SELECT count(*) AS count
                     FROM intake_documents
                    WHERE status <> 'completed'
                      AND (
                        original_name ILIKE '%%사업계획서%%'
                        OR (original_name ILIKE '%%PDM%%' AND lower(extension)='.pdf')
                      )"""
            ).fetchone()
        latest_count = int(latest["document_count"] or 0) if latest else 0
        pending_count = int(pending_authoritative["count"] or 0)
        should_create_early = latest is None
        should_refresh_final = source_count > latest_count and pending_count == 0
        if should_create_early or should_refresh_final:
            generate_project_overview()
    finally:
        _OVERVIEW_REFRESH_LOCK.release()

def event(
    conn, document_id, stage: str, status: str, message: str,
    details: dict | None = None, project_id=None,
) -> None:
    conn.execute(
        """INSERT INTO processing_events(document_id,stage,status,message,details,project_id)
           VALUES (%s,%s,%s,%s,%s,COALESCE(%s,NULLIF(current_setting('kodame.project_id',true),'')::uuid))""",
        (document_id, stage, status, message, Jsonb(details or {}), project_id),
    )

def claim_next() -> dict | None:
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """
            SELECT * FROM intake_documents
            WHERE (
              status IN ('queued','retry') AND available_at <= now()
            ) OR (
              status = 'processing' AND lease_until < now()
            ) OR (
              status = 'waiting_llm' AND available_at <= now()
            )
            ORDER BY queue_position
            FOR UPDATE SKIP LOCKED LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        next_stage = "analyzing" if row["status"] == "waiting_llm" and row.get("extracted_path") else "parsing"
        claimed = conn.execute(
            """UPDATE intake_documents
               SET status='processing', stage=%s, progress=%s, attempts=attempts+1,
                   worker_id=%s, lease_until=now()+interval '10 minutes',
                   started_at=COALESCE(started_at,now()), updated_at=now(), error_code=NULL, error_message=NULL
               WHERE id=%s RETURNING *""",
            (next_stage, 45 if next_stage == "analyzing" else 15, WORKER_ID, row["id"]),
        ).fetchone()
        event(conn, row["id"], next_stage, "started", "큐에서 안전하게 작업을 시작했습니다.", project_id=row["project_id"])
        return claimed

def update_stage(document_id, stage: str, progress: int, message: str) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "UPDATE intake_documents SET stage=%s, progress=%s, lease_until=now()+interval '10 minutes', updated_at=now() WHERE id=%s",
            (stage, progress, document_id),
        )
        event(conn, document_id, stage, "running", message)

def process(row: dict) -> None:
    document_id = row["id"]
    original_path = Path(row["stored_path"])
    try:
        extracted_path = row.get("extracted_path")
        if not extracted_path:
            update_stage(document_id, "parsing", 20, "문서 본문을 안전하게 추출하고 있습니다.")
            text, method = parse_document(original_path, row["extension"])
            EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
            destination = EXTRACTED_DIR / f"{document_id}.txt"
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(destination)
            with connection() as conn, conn.transaction():
                conn.execute(
                    "UPDATE intake_documents SET extracted_path=%s, extraction_method=%s, extracted_chars=%s, stage='stored', progress=40, updated_at=now() WHERE id=%s",
                    (str(destination), method, len(text), document_id),
                )
                event(conn, document_id, "stored", "completed", "추출 본문을 원본과 분리해 저장했습니다.", {"method": method, "characters": len(text)})
            time.sleep(WORKER_STEP_DELAY_SECONDS)
        else:
            text = Path(extracted_path).read_text(encoding="utf-8")

        update_stage(document_id, "analyzing", 55, "OpenRouter로 요약과 ODA 문서 유형을 분석하고 있습니다.")
        with llm_model_context(row.get("analysis_model")):
            analysis = analyze_document(row["original_name"], text)
        time.sleep(WORKER_STEP_DELAY_SECONDS)
        update_stage(document_id, "classifying", 80, "27개 섹션에 대한 다중 분류와 슬롯 후보를 생성하고 있습니다.")

        with connection() as conn, conn.transaction():
            conn.execute("DELETE FROM slot_suggestions WHERE document_id=%s", (document_id,))
            for match in analysis["section_matches"]:
                conn.execute(
                    """INSERT INTO slot_suggestions
                       (document_id,section_id,section_number,section_title,dac_criterion,category,confidence,rationale,evidence_quote,taxonomy_version,review_status,reviewed_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',now())
                       ON CONFLICT(document_id,section_id) DO UPDATE SET
                         confidence=excluded.confidence,rationale=excluded.rationale,evidence_quote=excluded.evidence_quote,
                         category=excluded.category,dac_criterion=excluded.dac_criterion,taxonomy_version=excluded.taxonomy_version,
                         review_status='approved',reviewed_at=now()""",
                    (document_id, match["section_id"], match["section_number"], match["section_title"],
                     match["dac_criterion"], match["category"], match["confidence"], match["rationale"],
                     match["evidence_quote"], TAXONOMY_VERSION),
                )
            conn.execute("DELETE FROM document_slot_assignments WHERE document_id=%s", (document_id,))
            for match in document_slot_matches(row["original_name"], analysis):
                conn.execute(
                    """INSERT INTO document_slot_assignments
                       (document_id,criterion,criterion_name,slot_id,slot_title,confidence,rationale)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(document_id,criterion) DO UPDATE SET
                         criterion_name=excluded.criterion_name,slot_id=excluded.slot_id,
                         slot_title=excluded.slot_title,confidence=excluded.confidence,rationale=excluded.rationale""",
                    (document_id, match["criterion"], match["criterion_name"], match["slot_id"],
                     match["slot_title"], match["confidence"], match["rationale"]),
                )
            conn.execute(
                """UPDATE intake_documents SET status='completed', stage='review', progress=100, summary=%s,
                   analysis=%s, lease_until=NULL, worker_id=NULL, completed_at=now(), updated_at=now() WHERE id=%s""",
                (str(analysis.get("summary", "")), Jsonb(analysis), document_id),
            )
            event(conn, document_id, "review", "completed", f"AI가 보고서 섹션 {len(analysis['section_matches'])}건과 PDM·DAC 슬롯을 자동 배정했습니다.")
        try:
            refresh_pdm_model(analyze_risks=False)
        except RuntimeError:
            # PDM 원본이 아직 큐에 없거나 표 추출 전이면 다음 문서 완료 시 다시 시도합니다.
            pass
        try:
            refresh_project_overview_if_needed()
        except RuntimeError:
            # 개요는 평가 실행 때도 최종 생성되므로 문서 처리 자체를 실패시키지 않습니다.
            pass
    except MissingApiKey as exc:
        with connection() as conn, conn.transaction():
            conn.execute(
                """UPDATE intake_documents SET status='waiting_llm',stage='waiting_llm',progress=45,
                   available_at=now()+interval '5 minutes',lease_until=NULL,worker_id=NULL,
                   error_code='OPENROUTER_KEY_MISSING',error_message=%s,updated_at=now() WHERE id=%s""",
                (str(exc), document_id),
            )
            event(conn, document_id, "waiting_llm", "paused", "본문 저장 완료. OpenRouter 키 설정을 기다립니다.")
    except (ParseError, AnalysisError) as exc:
        fail(document_id, type(exc).__name__, str(exc), row["attempts"])
    except Exception as exc:
        fail(document_id, type(exc).__name__, str(exc), row["attempts"], traceback.format_exc())

def fail(document_id, code: str, message: str, attempts: int, trace: str | None = None) -> None:
    retry = attempts < MAX_ATTEMPTS
    with connection() as conn, conn.transaction():
        conn.execute(
            """UPDATE intake_documents SET status=%s,stage=%s,progress=CASE WHEN %s THEN progress ELSE 100 END,
               available_at=now()+(%s * interval '1 minute'),lease_until=NULL,worker_id=NULL,
               error_code=%s,error_message=%s,updated_at=now() WHERE id=%s""",
            ("retry" if retry else "failed", "retry_wait" if retry else "failed", retry, min(30, 2 ** attempts), code, message[:2000], document_id),
        )
        event(conn, document_id, "error", "retry" if retry else "failed", message, {"trace": (trace or "")[-4000:]})

def main() -> None:
    open_pool()
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"KODAME intake worker {WORKER_ID} started (concurrency=1)")
    while True:
        with tenant_context(system=True):
            row = claim_next()
        if row:
            with tenant_context(row["project_id"], account_id=row.get("uploaded_by_account_id")):
                process(row)
        else:
            time.sleep(WORKER_POLL_SECONDS)

if __name__ == "__main__":
    main()
