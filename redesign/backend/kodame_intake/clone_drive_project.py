from __future__ import annotations

import argparse
import shutil
import uuid
from pathlib import Path

from psycopg.types.json import Jsonb

from .db import connection, open_pool, tenant_context
from .document_slots import document_slot_matches
from .pdm_monitoring import refresh_pdm_model
from .project_overview import generate_local_bootstrap_overview
from .settings import EXTRACTED_DIR, ORIGINALS_DIR


def _clone_one(source: dict, target_project_id: uuid.UUID) -> uuid.UUID:
    document_id = uuid.uuid4()
    destination_dir = ORIGINALS_DIR / str(target_project_id) / str(document_id)
    destination_dir.mkdir(parents=True, exist_ok=False)
    destination = destination_dir / source["original_name"]
    shutil.copy2(source["stored_path"], destination)
    extracted_path = None
    if source.get("extracted_path") and Path(source["extracted_path"]).is_file():
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        extracted_destination = EXTRACTED_DIR / f"{document_id}.txt"
        shutil.copy2(source["extracted_path"], extracted_destination)
        extracted_path = str(extracted_destination)

    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO intake_documents
               (id,original_name,stored_path,extracted_path,media_type,extension,size_bytes,sha256,
                status,stage,progress,attempts,extraction_method,extracted_chars,summary,analysis,
                analysis_model,completed_at,project_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'completed','review',100,%s,%s,%s,%s,%s,%s,now(),%s)""",
            (
                document_id, source["original_name"], str(destination), extracted_path,
                source.get("media_type"), source["extension"], source["size_bytes"], source["sha256"],
                source.get("attempts") or 1, source.get("extraction_method"), source.get("extracted_chars"),
                source.get("summary"), Jsonb(source.get("analysis") or {}), source.get("analysis_model"),
                target_project_id,
            ),
        )
        conn.execute(
            """INSERT INTO processing_events(document_id,stage,status,message,details,project_id)
               VALUES (%s,'review','completed',%s,%s,%s)""",
            (
                document_id,
                "Google Drive 원본과 해시를 대조해 순차 업로드·분석 결과를 복원했습니다.",
                Jsonb({"source": "google-drive", "source_document_id": str(source["id"]), "sha256": source["sha256"]}),
                target_project_id,
            ),
        )
        for match in document_slot_matches(source["original_name"], source.get("analysis") or {}):
            conn.execute(
                """INSERT INTO document_slot_assignments
                   (document_id,criterion,criterion_name,slot_id,slot_title,confidence,rationale,project_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(document_id,criterion) DO UPDATE SET
                     criterion_name=excluded.criterion_name,slot_id=excluded.slot_id,
                     slot_title=excluded.slot_title,confidence=excluded.confidence,rationale=excluded.rationale""",
                (
                    document_id, match["criterion"], match["criterion_name"], match["slot_id"],
                    match["slot_title"], match["confidence"], match["rationale"], target_project_id,
                ),
            )
    return document_id


def clone_project(source_project_id: uuid.UUID, target_project_id: uuid.UUID, generate_overview: bool) -> None:
    with tenant_context(system=True):
        with connection() as conn:
            target_count = conn.execute(
                "SELECT count(*) AS count FROM intake_documents WHERE project_id=%s", (target_project_id,)
            ).fetchone()["count"]
            if target_count:
                raise RuntimeError(f"대상 프로젝트가 비어 있지 않습니다: {target_count}개 문서")
            sources = conn.execute(
                "SELECT * FROM intake_documents WHERE project_id=%s ORDER BY queue_position", (source_project_id,)
            ).fetchall()
    if not sources:
        raise RuntimeError("복제할 원본 문서가 없습니다.")

    for index, source in enumerate(sources, 1):
        with tenant_context(system=True):
            _clone_one(source, target_project_id)
        print(f"[{index:02d}/{len(sources):02d}] {source['original_name']}", flush=True)

    with tenant_context(target_project_id):
        model_id = refresh_pdm_model()
        print(f"PDM 모델 갱신: {model_id}", flush=True)
        if generate_overview:
            overview_id = generate_local_bootstrap_overview()
            with connection() as conn, conn.transaction():
                row = conn.execute("SELECT overview FROM project_overviews WHERE id=%s", (overview_id,)).fetchone()
                project_name = ((row or {}).get("overview") or {}).get("project_name", {}).get("text", "").strip()
                if project_name and project_name != "확인 필요":
                    conn.execute("UPDATE projects SET name=%s,updated_at=now() WHERE id=%s", (project_name, target_project_id))
            print(f"사업개요 생성: {overview_id}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="이미 검증한 Google Drive 원본 문서를 빈 프로젝트로 순차 복원합니다.")
    parser.add_argument("source_project_id", type=uuid.UUID)
    parser.add_argument("target_project_id", type=uuid.UUID)
    parser.add_argument("--generate-overview", action="store_true")
    args = parser.parse_args()
    open_pool()
    clone_project(args.source_project_id, args.target_project_id, args.generate_overview)


if __name__ == "__main__":
    main()
