from __future__ import annotations

import os
import socket
import time
import traceback
import uuid
import signal
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import timedelta
from pathlib import Path
from threading import Lock, Event

from psycopg.types.json import Jsonb

from .db import connection, open_pool, tenant_context
from .document_slots import document_slot_matches
from .intake_control import attempt_context, check, IntakeStopped, finish_attempt
from .llm_models import llm_model_context
from .openrouter import AnalysisError, MissingApiKey, analyze_document
from .parsers import ParseError, parse_document
from .pdm_monitoring import refresh_pdm_model
from .project_overview import generate_project_overview, overview_source_document_count
from .settings import EXTRACTED_DIR, MAX_ATTEMPTS, TAXONOMY_VERSION, WORKER_POLL_SECONDS, WORKER_STEP_DELAY_SECONDS, WORKER_CONCURRENCY

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_OVERVIEW_REFRESH_LOCK = Lock()


def refresh_project_overview_if_needed(*, force=False) -> None:
    """Refresh the overview exclusively from completed project-plan uploads."""
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
                     FROM active_intake_documents
                    WHERE upload_role='project_plan'
                      AND status IN ('queued','retry','processing','waiting_llm')"""
            ).fetchone()
        latest_count = int(latest["document_count"] or 0) if latest else 0
        pending_count = int(pending_authoritative["count"] or 0)
        should_create_early = latest is None
        should_refresh_final = source_count > latest_count and pending_count == 0
        if should_create_early or should_refresh_final or force:
            generate_project_overview()
    finally:
        _OVERVIEW_REFRESH_LOCK.release()


def refresh_uploaded_foundation(role: str) -> None:
    """Keep the two foundation workflows independent of upload order."""
    if role == 'project_plan':
        refresh_project_overview_if_needed(force=True)
    elif role == 'pdm':
        refresh_pdm_model(analyze_risks=False)

def event(
    conn, document_id, stage: str, status: str, message: str,
    details: dict | None = None, project_id=None,
) -> None:
    conn.execute(
        """INSERT INTO processing_events(document_id,stage,status,message,details,project_id)
           VALUES (%s,%s,%s,%s,%s,COALESCE(%s,NULLIF(current_setting('kodame.project_id',true),'')::uuid))""",
        (document_id, stage, status, message, Jsonb(details or {}), project_id),
    )

def claim_next(*, exclude_ids=(), allow_foundation=True) -> dict | None:
    with connection() as conn, conn.transaction():
        conn.execute("UPDATE intake_documents SET status='cancelled',stage='cancelled',worker_id=NULL,lease_until=NULL,updated_at=now() WHERE status='processing' AND cancel_requested AND lease_until<now()")
        row = conn.execute(
            """
            SELECT * FROM active_intake_documents
            WHERE id <> ALL(%s::uuid[]) AND NOT cancel_requested AND ((
              status IN ('queued','retry') AND available_at <= now()
            ) OR (
              status = 'processing' AND lease_until < now()
            ) OR (
              status = 'waiting_llm' AND available_at <= now()
            ))
            ORDER BY queue_position
            FOR UPDATE SKIP LOCKED LIMIT 1
            """, (list(exclude_ids),)
        ).fetchone()
        if not row:
            return None
        if row.get('upload_role') != 'evidence' and not allow_foundation:
            # Drain earlier evidence before a foundation replacement. Do not
            # skip it and starve the replacement behind later evidence.
            return None
        next_stage = "analyzing" if row["status"] == "waiting_llm" and row.get("extracted_path") else "parsing"
        claimed = conn.execute(
            """UPDATE intake_documents
               SET status='processing', stage=%s, progress=%s, attempts=attempts+1,
                   worker_id=%s, run_token=%s, lease_until=now()+interval '10 minutes',
                   started_at=COALESCE(started_at,now()), updated_at=now(), error_code=NULL, error_message=NULL
               WHERE id=%s RETURNING *""",
            (next_stage, 45 if next_stage == "analyzing" else 15, WORKER_ID, uuid.uuid4(), row["id"]),
        ).fetchone()
        event(conn, row["id"], next_stage, "started", "큐에서 안전하게 작업을 시작했습니다.", project_id=row["project_id"])
        return claimed

def update_stage(document_id, stage: str, progress: int, message: str) -> None:
    with connection() as conn, conn.transaction():
        check(conn, lock=True)
        conn.execute(
            "UPDATE intake_documents SET stage=%s, progress=%s, lease_until=now()+interval '10 minutes', updated_at=now() WHERE id=%s",
            (stage, progress, document_id),
        )
        event(conn, document_id, stage, "running", message)

def process(row: dict) -> None:
    from .project_ai import get_project_model
    try:
        with attempt_context(row['id'], row.get('run_token')):
            model = get_project_model(row['project_id'])
            with connection() as conn, conn.transaction():
                check(conn, lock=True)
                conn.execute('UPDATE intake_documents SET analysis_model=%s WHERE id=%s', (model,row['id']))
            with llm_model_context(model):
                _process(row)
    except IntakeStopped:
        pass
    except Exception as exc:
        with attempt_context(row['id'], row.get('run_token')):
            try:
                fail(row["id"], type(exc).__name__, str(exc), row["attempts"], traceback.format_exc())
            except IntakeStopped:
                pass
    finally:
        with connection() as conn:
            conn.execute("UPDATE intake_documents SET status='cancelled',stage='cancelled',worker_id=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND run_token IS NOT DISTINCT FROM %s AND cancel_requested AND status='processing'", (row['id'],row.get('run_token')))


def _process(row: dict) -> None:
    document_id = row["id"]
    original_path = Path(row["stored_path"])
    try:
        from .document_eligibility import duplicate, complete_excluded, text_fingerprint, screening_context, VERSION as ELIGIBILITY_VERSION
        manual_include = (row.get('evaluation_scope') or {}).get('origin') == 'manual' and not row.get('evaluation_excluded')
        if not manual_include:
            with connection() as conn, conn.transaction():
                decision = duplicate(conn, row)
                if decision:
                    complete_excluded(conn, row, decision)
                    return
        extracted_path = row.get("extracted_path")
        if not extracted_path:
            update_stage(document_id, "parsing", 20, "문서 본문을 안전하게 추출하고 있습니다.")
            from .parse_sandbox import parse_isolated
            text, method = parse_isolated(original_path, row["extension"], full_text=True)
            check()
            EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
            destination = EXTRACTED_DIR / f"{document_id}.txt"
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(destination)
            with connection() as conn, conn.transaction():
                check(conn, lock=True)
                conn.execute(
                    "UPDATE intake_documents SET extracted_path=%s, extraction_method=%s, extracted_chars=%s, stage='stored', progress=40, updated_at=now() WHERE id=%s",
                    (str(destination), method, len(text), document_id),
                )
                event(conn, document_id, "stored", "completed", "추출 본문을 원본과 분리해 저장했습니다.", {"method": method, "characters": len(text)})
            time.sleep(WORKER_STEP_DELAY_SECONDS)
        else:
            text = Path(extracted_path).read_text(encoding="utf-8")

        text_hash = text_fingerprint(text)
        with connection() as conn, conn.transaction():
            check(conn, lock=True)
            conn.execute('UPDATE intake_documents SET normalized_text_sha256=%s WHERE id=%s', (text_hash, document_id))
            decision = duplicate(conn, row, text_hash) if not manual_include else None
            if decision:
                complete_excluded(conn, row, decision)
                return

        is_evidence = row.get('upload_role', 'evidence') == 'evidence'
        mode = row.get('intake_mode','auto')
        triage = row.get('triage')
        if is_evidence:
            from .intake_triage import classify, register_artifact, resolve_route
            update_stage(document_id, 'triaging', 45, '평가 포함 여부와 산출물·일반 자료 처리 방식을 사전 판단합니다.')
            triage = resolve_route(triage) if triage and (manual_include or (triage.get('evaluation_scope') or {}).get('version') == ELIGIBILITY_VERSION) else classify(
                row['original_name'], text, evaluation_context=screening_context())
            with connection() as conn, conn.transaction():
                check(conn, lock=True)
                conn.execute('UPDATE intake_documents SET triage=%s WHERE id=%s',(Jsonb(triage),document_id))
                decision = triage.get('evaluation_scope') or {}
                if not manual_include and decision.get('excluded'):
                    complete_excluded(conn, row, decision, triage=triage)
                    return
                if not manual_include:
                    conn.execute('UPDATE intake_documents SET evaluation_scope=%s WHERE id=%s', (Jsonb(decision),document_id))
            if mode == 'auto':
                mode = triage['kind']
        update_stage(document_id, "analyzing", 55, '산출물 기본 정보와 관련 항목을 등록합니다.' if mode=='artifact' else "OpenRouter로 요약과 ODA 문서 유형을 분석하고 있습니다.")
        analysis = register_artifact(row['original_name'],text,triage) if is_evidence and mode=='artifact' else analyze_document(row["original_name"], text, upload_role=row.get('upload_role', 'evidence'))
        from .ai.prompt_registry import prompt_manifest
        analysis['prompt_versions'] = prompt_manifest()
        if row.get('upload_role') == 'project_plan':
            from .foundation_facts import extract_plan_facts
            update_stage(document_id, 'analyzing', 62, '사업계획서 전체에서 개요 필드별 사실과 원문 위치를 저장합니다.')
            analysis['overview_facts'] = extract_plan_facts(text)
        if is_evidence:
            analysis.update(intake_mode=mode,triage=triage)
        if is_evidence and mode != 'artifact':
            from .evidence_matching import match_foundations
            update_stage(document_id, 'analyzing', 68, '사업 맥락과 PDM 지표별 사실·종료평가 근거를 원문에서 추출하고 있습니다.')
            matches = match_foundations(text)
            analysis['evidence_matches'] = {**matches,
                'dac_slots': (analysis.get('content_classification') or {}).get('slot_matches', []),
                'report_sections': analysis.get('section_matches', [])}
        elif not is_evidence:
            # Foundation uploads retain their existing analysis pipeline.
            from .dac_evidence import analyze_document as index_dac_document
            update_stage(document_id, 'analyzing', 68, 'DAC 55개 세부기준에 사용할 원문 근거와 위치를 분석하고 있습니다.')
            analysis['dac_fulltext'] = index_dac_document({
                'id':str(document_id), 'name':row['original_name'], 'summary':analysis.get('summary',''),
                'assigned_criteria':analysis.get('dac_criteria',[]), 'review_all':True,
                'extracted_path':str(extracted_path or destination), 'stored_path':str(original_path),
                'extension':row['extension'], 'sha256':row['sha256'],
                'dac_fulltext_cache':(row.get('analysis') or {}).get('dac_fulltext')})
            analysis['dac_criteria'] = sorted(set(analysis.get('dac_criteria',[])) | {
                q.split('-q')[0] for q in analysis['dac_fulltext']['question_ids']})
        if is_evidence:
            register = (analysis.get('evidence_matches') or {}).get('registration_facts') or {}
            analysis['registration_facts'] = register
            contextual_summary = register.get('summary')
            if contextual_summary:
                analysis['general_summary'] = analysis.get('summary', '')
                analysis['summary'] = contextual_summary
                if mode == 'artifact':
                    analysis['summary'] += '\n' + analysis.get('registration', {}).get('limitation', '')
            analysis['dac_criteria'] = sorted(set(analysis.get('dac_criteria', [])) | {
                q.rsplit('-q', 1)[0] for fact in register.get('facts', []) for q in fact['dac_question_ids']})
        time.sleep(WORKER_STEP_DELAY_SECONDS)
        update_stage(document_id, "classifying", 80, "27개 섹션에 대한 다중 분류와 슬롯 후보를 생성하고 있습니다.")

        with connection() as conn, conn.transaction():
            from .foundation import promote
            from .project_lifecycle import lock_project_workflow
            lock_project_workflow(conn)
            check(conn, lock=True)
            # Two identical files may finish concurrently. The project lock and
            # completed canonical source prevent duplicate evaluation contributions.
            decision = duplicate(conn, row, text_hash) if not manual_include else None
            if decision:
                complete_excluded(conn, row, decision, triage=triage)
                return
            from .source_locations import attach_locations
            attach_locations(analysis, text)
            promote(conn, document_id, row.get('upload_role', 'evidence'))
            if is_evidence:
                from .evidence_matching import save_pdm_assignments
                save_pdm_assignments(conn, document_id, analysis['evidence_matches'])
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
                   analysis=%s, error_code=NULL,error_message=NULL,lease_until=NULL, worker_id=NULL, completed_at=now(), updated_at=now() WHERE id=%s""",
                (str(analysis.get("summary", "")), Jsonb(analysis), document_id),
            )
            event(conn, document_id, "review", "completed",
                  '사업 맥락 요약과 PDM 지표별 사실·종료평가 정보 및 연결 항목을 저장했습니다. 성과 분석과 DAC 평가는 각 화면에서 실행해 주세요.'
                  if is_evidence else f"AI가 보고서 섹션 {len(analysis['section_matches'])}건과 PDM·DAC 슬롯을 자동 배정했습니다.")
        if is_evidence:
            return
        # The document transaction is complete; subsequent foundation refreshes
        # have their own workflow guards rather than the completed intake token.
        finish_attempt()
        try:
            refresh_uploaded_foundation(row.get('upload_role'))
        except RuntimeError:
            # 개요는 평가 실행 때도 최종 생성되므로 문서 처리 자체를 실패시키지 않습니다.
            pass
    except MissingApiKey as exc:
        with connection() as conn, conn.transaction():
            check(conn, lock=True)
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
    retry = attempts < MAX_ATTEMPTS and code not in ('BudgetExceeded', 'ParseLimitExceeded')
    with connection() as conn, conn.transaction():
        check(conn, lock=True)
        conn.execute(
            """UPDATE intake_documents SET status=%s,stage=%s,progress=CASE WHEN %s THEN progress ELSE 100 END,
               available_at=now()+(%s * interval '1 minute'),lease_until=NULL,worker_id=NULL,
               error_code=%s,error_message=%s,updated_at=now() WHERE id=%s""",
            ("retry" if retry else "failed", "retry_wait" if retry else "failed", retry, min(30, 2 ** attempts), code, message[:2000], document_id),
        )
        event(conn, document_id, "error", "retry" if retry else "failed", message, {"trace": (trace or "")[-4000:]})

def process_in_tenant(row):
    # ThreadPoolExecutor does not propagate ContextVars. Establish all tenant,
    # account, model and attempt scopes inside each worker thread.
    from .ai.job_budget import job_budget
    with tenant_context(row['project_id'], account_id=row.get('uploaded_by_account_id')), job_budget(row.get('run_token')):
        process(row)


def renew_leases(rows):
    with tenant_context(system=True), connection() as conn:
        for row in rows:
            conn.execute("""UPDATE intake_documents SET lease_until=now()+interval '10 minutes'
                WHERE id=%s AND run_token=%s AND status='processing' AND worker_id=%s""",
                (row['id'],row['run_token'],WORKER_ID))


def run_queue(stop, *, concurrency=WORKER_CONCURRENCY):
    from .project_deletion import cleanup_files
    pending = {}
    last_maintenance = 0
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='intake') as executor:
        while not stop.is_set() or pending:
            Path('/tmp/kodame-intake-heartbeat').touch()
            for future in list(pending):
                if future.done():
                    del pending[future]
                    try:
                        future.result()
                    except Exception:
                        traceback.print_exc()  # A failed document cannot stop the queue.
            if time.monotonic()-last_maintenance >= 30:
                renew_leases(list(pending.values()))
                cleanup_files()
                last_maintenance = time.monotonic()
            while not stop.is_set() and len(pending) < concurrency:
                if any(row.get('upload_role') != 'evidence' for row in pending.values()):
                    break
                with tenant_context(system=True):
                    row = claim_next(exclude_ids=[row['id'] for row in pending.values()], allow_foundation=not pending)
                if not row:
                    break
                pending[executor.submit(process_in_tenant,row)] = row
            if pending:
                wait(pending,timeout=WORKER_POLL_SECONDS,return_when=FIRST_COMPLETED)
            elif not stop.is_set():
                stop.wait(WORKER_POLL_SECONDS)


def main() -> None:
    from .db import pool
    if os.getenv('RUN_MIGRATIONS_ON_START', 'true').lower() == 'true':
        open_pool()
    else:
        pool.open(wait=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    print(f"KODAME intake worker {WORKER_ID} started (evidence concurrency={WORKER_CONCURRENCY}, foundation=exclusive)",flush=True)
    try:
        run_queue(stop)
    finally:
        pool.close()

if __name__ == "__main__":
    main()
