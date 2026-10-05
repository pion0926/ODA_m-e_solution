from __future__ import annotations
import hashlib
import os
import shutil
import uuid
from pathlib import Path
import aiofiles
from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from ..db import connection, current_project_id
from ..document_slots import DOCUMENT_SLOTS
from ..foundation import ROLES as FOUNDATION_ROLES, state as foundation_state, validate_upload
from ..settings import ALLOWED_EXTENSIONS, MAX_FILE_BYTES, ORIGINALS_DIR, TAXONOMY_VERSION
from ..settings import WORKER_CONCURRENCY
from ..project_lifecycle import active_workflow_jobs, lock_project_workflow
from ..taxonomy import DAC_CRITERIA, SECTIONS
from .dependencies import SAMPLE_TEMPLATE_FILES, _request_account_id, _request_llm_model, _sample_template_root, clean_filename, serialize_document
from .schemas import IntakeModeRequest, EvaluationScopeRequest
from fastapi import APIRouter
router = APIRouter()


@router.get("/api/v2/intake/taxonomy")
def taxonomy():
    return {"version": TAXONOMY_VERSION, "dac_criteria": DAC_CRITERIA, "sections": [
        {"number": n, "id": sid, "title": title, "classification_rule": rule} for n, sid, title, rule in SECTIONS
    ]}


@router.get('/api/v2/intake/foundation')
def get_foundation():
    return foundation_state()


@router.get('/api/v2/intake/foundation/{role}/impact')
def foundation_impact(role: str):
    from ..foundation import replacement_impact
    with connection() as conn:
        return replacement_impact(conn, role)


@router.get('/api/v2/intake/foundation/history')
def foundation_history():
    with connection() as conn:
        return {'items': conn.execute('SELECT * FROM foundation_changes ORDER BY created_at DESC').fetchall()}


@router.post("/api/v2/intake/uploads", status_code=202)
async def upload_documents(request: Request, files: list[UploadFile] = File(...)):
    role = request.query_params.get('role', 'evidence')
    replaces = request.query_params.get('replaces', '')
    change_reason = request.query_params.get('change_reason', '').strip()
    impact_revision = request.query_params.get('impact_revision', '')
    if replaces and (not change_reason or len(change_reason) > 1000):
        raise HTTPException(422, '기준 문서 교체 사유를 1~1000자로 기록해 주세요.')
    if role not in ('evidence', *FOUNDATION_ROLES):
        raise HTTPException(400, '올바른 업로드 구분을 선택해 주세요.')
    if role in FOUNDATION_ROLES and len(files) != 1:
        raise HTTPException(400, '기준 문서는 한 번에 한 파일만 업로드할 수 있습니다.')
    if not files or len(files) > 100:
        raise HTTPException(400, "한 번에 1~100개 파일을 선택하세요.")
    with connection() as conn, conn.transaction():
        validate_upload(conn, role, replaces)
    accepted = []
    rejected = []
    for upload in files:
        safe_name = clean_filename(upload.filename or "document")
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            rejected.append({"file_name": safe_name, "status": 415, "error": "지원하지 않는 파일 형식입니다."})
            await upload.close()
            continue
        document_id = uuid.uuid4()
        directory = ORIGINALS_DIR / str(current_project_id()) / str(document_id)
        destination = directory / safe_name
        temporary = directory / ".uploading"
        digest = hashlib.sha256()
        size = 0
        committed = False
        try:
            directory.mkdir(parents=True, exist_ok=False)
            async with aiofiles.open(temporary, "wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise HTTPException(413, f"파일 크기 제한을 초과했습니다: {safe_name}")
                    digest.update(chunk)
                    await output.write(chunk)
            if size == 0:
                raise HTTPException(422, "내용이 없는 빈 파일입니다.")
            os.replace(temporary, destination)
            try:
                os.chmod(destination, 0o440)
            except OSError:
                pass
            deduplicated = False
            with connection() as conn, conn.transaction():
                validate_upload(conn, role, replaces)
                impact = None
                if replaces:
                    from ..foundation import replacement_impact
                    impact = replacement_impact(conn, role)
                    if impact['revision'] != impact_revision:
                        raise HTTPException(409, '교체 영향이 변경되었습니다. 최신 영향 목록을 확인해 주세요.')
                row = conn.execute(
                    """INSERT INTO intake_documents
                       (id,original_name,stored_path,media_type,extension,size_bytes,sha256,analysis_model,uploaded_by_account_id,upload_role)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (project_id,original_name,sha256,upload_role) WHERE superseded_at IS NULL DO NOTHING
                       RETURNING *""",
                    (document_id, safe_name, str(destination), upload.content_type, extension, size,
                     digest.hexdigest(), _request_llm_model(request), _request_account_id(request), role),
                ).fetchone()
                if row:
                    if role in FOUNDATION_ROLES:
                        conn.execute('''INSERT INTO foundation_changes(document_id,previous_document_id,role,reason,approved_by,impact)
                            VALUES (%s,%s,%s,%s,%s,%s)''',
                            (document_id, replaces or None, role, change_reason or '최초 등록',
                             _request_account_id(request), Jsonb(impact or {})))
                    conn.execute(
                        "INSERT INTO processing_events(document_id,stage,status,message,details) VALUES (%s,'queued','queued',%s,%s)",
                        (document_id, "원본 저장과 무결성 검증 후 처리 큐에 등록했습니다.", Jsonb({"sha256": digest.hexdigest()})),
                    )
                else:
                    row = conn.execute(
                        "SELECT * FROM active_intake_documents WHERE original_name=%s AND sha256=%s AND upload_role=%s",
                        (safe_name, digest.hexdigest(), role),
                    ).fetchone()
                    deduplicated = True
            committed = True
            if deduplicated:
                shutil.rmtree(directory)
            accepted.append({**serialize_document(row), "deduplicated": deduplicated})
        except Exception as exc:
            # A connection failure at COMMIT can be ambiguous. Only remove the
            # generated directory if the database confirms it is unreferenced.
            unreferenced = not destination.exists()
            if not committed and destination.exists():
                try:
                    with connection() as conn:
                        saved = conn.execute("SELECT * FROM active_intake_documents WHERE id=%s", (document_id,)).fetchone()
                    if saved:
                        row, deduplicated = saved, False
                        accepted.append({**serialize_document(saved), "deduplicated": False})
                        committed = True
                    else:
                        unreferenced = True
                except Exception:
                    pass  # Retain the original for recovery when DB is unavailable.
            if unreferenced and directory.resolve().parent == (ORIGINALS_DIR / str(current_project_id())).resolve():
                if directory.is_dir():
                    try:
                        shutil.rmtree(directory)
                    except OSError:
                        pass  # Keep a recoverable orphan; still report this file's result.
            if not committed:
                rejected.append({"file_name": safe_name, "status": exc.status_code if isinstance(exc, HTTPException) else 503,
                                 "error": str(exc.detail) if isinstance(exc, HTTPException) else "접수 여부를 확인하지 못했습니다. 목록 확인 후 다시 업로드해 주세요. 동일 파일은 중복 등록되지 않습니다."})
            elif not any(item["id"] == str(row["id"]) for item in accepted):
                accepted.append({**serialize_document(row), "deduplicated": deduplicated})
        finally:
            await upload.close()
    return {"accepted": accepted, "count": len(accepted), "rejected": rejected, "rejected_count": len(rejected)}


@router.get("/api/v2/intake/jobs")
def list_jobs(limit: int = 100, before: int | None = None):
    limit = max(1, min(limit, 200))
    with connection() as conn:
        rows = conn.execute("SELECT * FROM active_intake_documents WHERE (%s::bigint IS NULL OR queue_position < %s) ORDER BY queue_position DESC LIMIT %s", (before, before, limit + 1)).fetchall()
        counts = {row["status"]: row["count"] for row in conn.execute("SELECT status,count(*) AS count FROM active_intake_documents GROUP BY status").fetchall()}
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [serialize_document(row) for row in rows], "count": len(rows), "total": sum(counts.values()),
            "status_counts": counts, "next_before": rows[-1]["queue_position"] if more else None, "worker_concurrency": WORKER_CONCURRENCY}


@router.get("/api/v2/intake/jobs/{document_id}")
def get_job(document_id: uuid.UUID):
    with connection() as conn:
        row = conn.execute("SELECT * FROM active_intake_documents WHERE id=%s", (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, "문서를 찾을 수 없습니다.")
        events = conn.execute("SELECT stage,status,message,created_at FROM processing_events WHERE document_id=%s ORDER BY id", (document_id,)).fetchall()
    result = serialize_document(row)
    result["analysis"] = row.get("analysis")
    result["events"] = [{**event, "created_at": event["created_at"].isoformat()} for event in events]
    return result


@router.get("/api/v2/intake/jobs/{document_id}/download")
def download_original_document(document_id: uuid.UUID, inline: bool = False):
    with connection() as conn:
        row = conn.execute(
            "SELECT original_name,stored_path,media_type FROM intake_documents WHERE id=%s",
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")

    path = Path(row["stored_path"]).resolve()
    originals_root = ORIGINALS_DIR.resolve()
    if originals_root not in path.parents or not path.is_file():
        raise HTTPException(404, "원본 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type=row.get("media_type") or "application/octet-stream",
        filename=row["original_name"],
        content_disposition_type='inline' if inline and path.suffix.lower() == '.pdf' else 'attachment',
    )


@router.get('/api/v2/intake/jobs/{document_id}/source')
def source_evidence(document_id: uuid.UUID, start: int = 0, end: int | None = None):
    from ..settings import EXTRACTED_DIR
    with connection() as conn:
        row = conn.execute('SELECT original_name,extracted_path,analysis FROM intake_documents WHERE id=%s', (document_id,)).fetchone()
    if not row or not row['extracted_path']:
        raise HTTPException(404, '추출 원문이 없습니다.')
    path = Path(row['extracted_path']).resolve()
    if EXTRACTED_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, '추출 원문을 찾을 수 없습니다.')
    text = path.read_text(encoding='utf-8')
    start = max(0, min(start, len(text)))
    end = max(start, min(end if end is not None else start + 5000, start + 20000, len(text)))
    from ..source_locations import locate
    return {'document_id': str(document_id), 'file_name': row['original_name'],
            'start': start, 'end': end, 'total_chars': len(text), 'text': text[start:end],
            'location': locate(text, text[start:end], start=start),
            'facts': (row.get('analysis') or {}).get('registration_facts', {}).get('facts', []) +
                     (row.get('analysis') or {}).get('overview_facts', {}).get('facts', [])}


@router.get("/api/v2/samples/templates/{template_id}/download")
def download_sample_template(template_id: str):
    filename = SAMPLE_TEMPLATE_FILES.get(template_id)
    if not filename:
        raise HTTPException(404, "샘플서식을 찾을 수 없습니다.")
    root = _sample_template_root()
    path = (root / filename).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "샘플서식 파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.post('/api/v2/intake/jobs/{document_id}/cancel', status_code=202)
def cancel_intake_job(document_id: uuid.UUID):
    with connection() as conn, conn.transaction():
        lock_project_workflow(conn)
        row = conn.execute("""UPDATE intake_documents SET cancel_requested=true,
            status=CASE WHEN status='processing' THEN status ELSE 'cancelled' END,
            stage=CASE WHEN status='processing' THEN 'cancelling' ELSE 'cancelled' END,
            updated_at=now() WHERE id=%s AND superseded_at IS NULL
            AND status IN ('queued','retry','waiting_llm','processing','cancelled','awaiting_review') RETURNING *""", (document_id,)).fetchone()
        if not row:
            raise HTTPException(409, '현재 상태에서는 중지할 수 없습니다.')
    return serialize_document(row)


@router.put('/api/v2/intake/jobs/{document_id}/mode', status_code=202)
def set_intake_mode(document_id: uuid.UUID, payload: IntakeModeRequest):
    with connection() as conn, conn.transaction():
        lock_project_workflow(conn)
        row = conn.execute('SELECT * FROM active_intake_documents WHERE id=%s FOR UPDATE',(document_id,)).fetchone()
        if not row or row['upload_role'] != 'evidence':
            raise HTTPException(409,'일반 업로드 문서만 처리 방식을 변경할 수 있습니다.')
        if row.get('evaluation_excluded'):
            raise HTTPException(409, '평가 대상에 다시 포함한 뒤 처리 방식을 변경해 주세요.')
        if row['status']=='processing' or row['updated_at'].isoformat()!=payload.expected_updated_at:
            raise HTTPException(409,'문서 상태가 변경되었거나 처리 중입니다. 중지 완료 후 최신 상태에서 선택해 주세요.')
        from ..project_lifecycle import active_workflow_jobs
        if active_workflow_jobs(conn):
            raise HTTPException(409,'성과 분석·DAC 평가·보고서 작업 완료 후 처리 방식을 변경해 주세요.')
        for table in ('document_slot_assignments','pdm_document_assignments','slot_suggestions'):
            conn.execute(f'DELETE FROM {table} WHERE document_id=%s',(document_id,))
        row = conn.execute("""UPDATE intake_documents SET intake_mode=%s,status='queued',stage='queued',progress=0,
            analysis=NULL,summary=NULL,analysis_model=NULL,cancel_requested=false,run_token=NULL,
            attempts=0,worker_id=NULL,lease_until=NULL,available_at=now(),completed_at=NULL,
            error_code=NULL,error_message=NULL,updated_at=now() WHERE id=%s RETURNING *""",(payload.mode,document_id)).fetchone()
    return serialize_document(row)


@router.put('/api/v2/intake/jobs/{document_id}/evaluation-scope')
def set_evaluation_scope(document_id: uuid.UUID, payload: EvaluationScopeRequest):
    from ..document_eligibility import VERSION
    if not payload.reason.strip():
        raise HTTPException(422, '변경 사유를 입력해 주세요.')
    with connection() as conn, conn.transaction():
        lock_project_workflow(conn)
        row = conn.execute('SELECT * FROM active_intake_documents WHERE id=%s FOR UPDATE', (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, '문서를 찾을 수 없습니다.')
        if row['upload_role'] != 'evidence':
            raise HTTPException(409, '기준 문서는 제외할 수 없습니다. 기준 문서 교체 기능을 이용해 주세요.')
        if row['updated_at'].isoformat() != payload.expected_updated_at or row['status'] == 'processing':
            raise HTTPException(409, '문서 상태가 변경되었거나 분석 중입니다. 중지 완료 후 다시 확인해 주세요.')
        if active_workflow_jobs(conn):
            raise HTTPException(409, '성과 분석·DAC 평가·보고서 작업 완료 후 평가 대상을 변경해 주세요.')
        decision = {'version': VERSION, 'excluded': payload.excluded, 'origin': 'manual',
                    'code': 'manual', 'reason': payload.reason.strip()}
        if payload.excluded:
            row = conn.execute('''UPDATE intake_documents SET evaluation_excluded=true,evaluation_scope=%s,
                status='completed',stage='excluded',progress=100,cancel_requested=false,
                error_code=NULL,error_message=NULL,run_token=NULL,worker_id=NULL,lease_until=NULL,
                completed_at=now(),updated_at=now() WHERE id=%s RETURNING *''', (Jsonb(decision),document_id)).fetchone()
        else:
            # Inclusion must run the analysis that early exclusion intentionally skipped.
            row = conn.execute('''UPDATE intake_documents SET evaluation_excluded=false,evaluation_scope=%s,
                status='queued',stage='queued',progress=0,cancel_requested=false,attempts=0,available_at=now(),
                error_code=NULL,error_message=NULL,run_token=NULL,worker_id=NULL,lease_until=NULL,
                completed_at=NULL,updated_at=now() WHERE id=%s RETURNING *''', (Jsonb(decision),document_id)).fetchone()
        conn.execute('''INSERT INTO processing_events(document_id,stage,status,message,details)
            VALUES (%s,'evaluation_scope','completed',%s,%s)''',
            (document_id, ('평가 대상에서 제외: ' if payload.excluded else '평가 대상 포함·분석 대기: ') + payload.reason.strip(), Jsonb(decision)))
    return serialize_document(row)


@router.post("/api/v2/intake/jobs/{document_id}/retry", status_code=202)
def retry_job(document_id: uuid.UUID, request: Request):
    with connection() as conn, conn.transaction():
        lock_project_workflow(conn)
        candidate = conn.execute('SELECT upload_role FROM active_intake_documents WHERE id=%s', (document_id,)).fetchone()
        if candidate and candidate['upload_role'] in FOUNDATION_ROLES:
            latest = foundation_state(conn)['documents'].get(candidate['upload_role'])
            if not latest or latest['id'] != str(document_id):
                raise HTTPException(409, '새 기준 문서가 등록되어 이전 문서를 재시도할 수 없습니다.')
        row = conn.execute(
            """UPDATE intake_documents SET status='retry',stage='queued',progress=CASE WHEN extracted_path IS NULL THEN 0 ELSE 45 END,
               analysis_model=NULL,cancel_requested=false,run_token=NULL,attempts=0,worker_id=NULL,lease_until=NULL,
               available_at=now(),error_code=NULL,error_message=NULL,updated_at=now()
               WHERE id=%s AND superseded_at IS NULL AND status IN ('failed','waiting_llm','cancelled') RETURNING *""",
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(409, "현재 상태에서는 재시도할 수 없습니다.")
    return serialize_document(row)


@router.get("/api/v2/intake/suggestions")
def list_suggestions(status: str = "pending"):
    with connection() as conn:
        rows = conn.execute(
            """SELECT s.*,d.original_name,d.size_bytes,d.summary FROM slot_suggestions s
               JOIN evaluation_intake_documents d ON d.id=s.document_id WHERE s.review_status=%s
               ORDER BY s.created_at DESC,s.confidence DESC""", (status,)
        ).fetchall()
    return {"items": [{**row, "document_id": str(row["document_id"]), "confidence": float(row["confidence"]),
                       "created_at": row["created_at"].isoformat(), "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None} for row in rows], "count": len(rows)}


@router.get("/api/v2/intake/document-slots")
def list_document_slots():
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.*,d.original_name,d.size_bytes,d.summary
               FROM document_slot_assignments a JOIN evaluation_intake_documents d ON d.id=a.document_id
               ORDER BY a.criterion,a.slot_id,d.original_name"""
        ).fetchall()
    items = [{**row, "document_id": str(row["document_id"]), "confidence": float(row["confidence"]),
              "created_at": row["created_at"].isoformat()} for row in rows]
    criteria = [{"id": key, "name": value["name"], "need": value["need"],
                 "slots": [{"id": sid, "title": title} for sid, title in value["slots"]]}
                for key, value in DOCUMENT_SLOTS.items()]
    return {"criteria": criteria, "items": items, "count": len(items)}


@router.post("/api/v2/intake/suggestions/approve-all")
def approve_all_suggestions():
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """WITH approved AS (
                   UPDATE slot_suggestions
                      SET review_status='approved',reviewed_at=now()
                    WHERE review_status='pending'
                RETURNING id)
               SELECT count(*) AS count FROM approved"""
        ).fetchone()
    return {"status": "approved", "count": row["count"]}


@router.post("/api/v2/intake/suggestions/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: int):
    with connection() as conn, conn.transaction():
        row = conn.execute(
            "UPDATE slot_suggestions SET review_status='approved',reviewed_at=now() WHERE id=%s AND review_status='pending' RETURNING id,review_status,reviewed_at",
            (suggestion_id,),
        ).fetchone()
    if not row:
        raise HTTPException(409, "이미 검토됐거나 존재하지 않는 제안입니다.")
    return row
