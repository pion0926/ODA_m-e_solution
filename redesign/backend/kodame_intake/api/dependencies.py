from __future__ import annotations
import os
import re
from pathlib import Path
from fastapi import HTTPException, Request
from ..db import tenant_context
from ..hwpx_pipeline import hwpx_authoring_contract
from ..llm_models import llm_model_context
from ..project_ai import get_project_model
from ..openrouter import clean_risk_text
from ..presentation_exporter import SLIDE_COUNT
from ..report_sections import section_documents, section_reference_route
from ..project_lifecycle import active_workflow_jobs, lock_project_workflow


def clean_filename(name: str) -> str:
    base = Path(name or "document").name
    base = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", base).strip(" .")
    return base[:180] or "document"


def _clean_risk_payload(value):
    if isinstance(value, dict):
        return {key: _clean_risk_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_risk_payload(item) for item in value]
    if isinstance(value, str):
        return clean_risk_text(value)
    return value


def serialize_document(row: dict) -> dict:
    return {
        "id": str(row["id"]), "file_name": row["original_name"], "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "upload_role": row.get('upload_role', 'evidence'),
        "evaluation_excluded": row.get('evaluation_excluded', False),
        "evaluation_scope": row.get('evaluation_scope') or {},
        "has_extracted_text": bool(row.get('extracted_path')),
        "matches": {axis: [{key: item[key] for key in ('topic','indicator_id','indicator','slot_id','section_id','section_title','confidence','rationale') if key in item}
                           for item in (row.get('analysis') or {}).get('evidence_matches', {}).get(axis, [])]
                    for axis in ('project_plan','pdm','dac_slots','report_sections')},
        "status": row["status"], "stage": row["stage"], "progress": row["progress"],
        "cancel_requested": row.get('cancel_requested', False), "analysis_model": row.get('analysis_model'),
        "intake_mode": (row.get('analysis') or {}).get('intake_mode') or row.get('intake_mode','auto'),
        "triage": row.get('triage'), "registration": (row.get('analysis') or {}).get('registration'),
        "intake_warnings": (row.get('analysis') or {}).get('quality_flags',[]) if (row.get('analysis') or {}).get('intake_mode')=='artifact' else [],
        "queue_position": row["queue_position"], "summary": row.get("summary"),
        "registration_fact_count": len(((row.get('analysis') or {}).get('registration_facts') or {}).get('facts', [])),
        "review_depth": 'sample_only' if (row.get('analysis') or {}).get('intake_mode') == 'artifact' else 'full_extracted_text',
        "error_code": row.get("error_code"), "error_message": row.get("error_message"),
        "uploaded_at": row["uploaded_at"].isoformat(), "updated_at": row["updated_at"].isoformat(),
    }


SAMPLE_TEMPLATE_FILES = {
    "user-manual": "user-guide-current.pdf",
    "evaluation-report-hwpx": "5-1. 종료평가 결과보고서 양식.hwpx",
    "evaluation-report-hwp": "koica-v2.2-20260919/forms/5-1. 종료평가 결과보고서 양식.hwp",
    "evaluation-grade-xlsx": "koica-v2.2-20260919/5-2. 종료평가 등급 결과표(엑셀버전).xlsx",
    "evaluation-grade-hwp": "koica-v2.2-20260919/forms/5-2. 종료평가 등급 결과표(한글버전).hwp",
    "evaluation-feedback-xlsm": "koica-v2.2-20260919/forms/5-4. 평가 환류과제 이행방안 양식.xlsm",
    "evaluation-guide-v22": "koica-v2.2-20260919/평가 업무수행 길라잡이 v2.2.pdf",
    "evaluation-lessons-pptx": "5-3. 분야별 평가 교훈 리포트 양식.pptx",
    "consultant-consent-hwp": "5-6. 현지 평가 컨설턴트 개인정보 수집 및 활용동의서_국영문.hwp",
    "evaluation-faq-hwp": "9. 평가업무수행 길라잡이 FAQ.hwp",
}


def _sample_template_root() -> Path:
    configured = Path(os.getenv("SAMPLES_DIR", "/app/samples"))
    if configured.is_dir():
        return configured.resolve()
    return next((parent / "samples" for parent in Path(__file__).resolve().parents
                 if (parent / "samples").is_dir()), configured).resolve()


PUBLIC_API_PATHS = {
    "/healthz",
    "/api/v2/auth/login",
    "/api/v2/auth/register",
    "/api/v2/auth/logout",
    "/api/v2/auth/me",
}


ACCOUNT_ONLY_API_PATHS = {
    "/api/v2/account/settings",
}


REPORT_API_PREFIX = "/api/v2/report"


def _run_background_for_account(task, account_id, project_id, *args, model=None):
    with tenant_context(project_id, account_id=account_id), llm_model_context(model):
        task(*args)


def _reserve_project_workflow(conn) -> None:
    lock_project_workflow(conn)
    if active_workflow_jobs(conn):
        raise HTTPException(409, "현재 프로젝트에서 평가·보고서 작업이 진행 중입니다. 완료 후 다시 실행해 주세요.")


def _request_account_id(request: Request):
    session = request.state.auth
    if not session:
        raise HTTPException(401, "로그인이 필요합니다.")
    return session["account_id"]


def _request_llm_model(request: Request) -> str:
    return request.state.llm_model or get_project_model()


def serialize_report_section(row: dict, with_documents: bool = False) -> dict:
    if row['part_id'] == 'cover':
        from report_prompts import EDITOR_REPORT_PARTS
        definition = next(item for item in EDITOR_REPORT_PARTS if item['id'] == 'cover')
        row = {**row, 'prompt': definition['prompt'], 'required_inputs': definition['requiredInputs']}
    result = {
        "part_id": row["part_id"], "section_number": row["section_number"],
        "section_id": row["section_id"], "title": row["title"], "prompt": row["prompt"],
        "required_inputs": row["required_inputs"], "content": row["content"], "status": row["status"],
        "source_document_ids": row["source_document_ids"], "generation_model": row["generation_model"],
        "generation_metadata": row.get("generation_metadata") or {},
        "quality_score": float(row["quality_score"]) if row.get("quality_score") is not None else None,
        "quality_report": row.get("quality_report") or {},
        "content_storage": "report_sections.content",
        "reference_contract": section_reference_route(row["part_id"]),
        "hwpx_contract": hwpx_authoring_contract(row["part_id"]),
        "error_message": row["error_message"],
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }
    if with_documents:
        result["documents"] = section_documents(row["part_id"])
        if row['part_id'] == 'cover':
            result['source_document_ids'] = [doc['id'] for doc in result['documents']]
    return result


def serialize_generation_run(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "total_sections": row["total_sections"],
        "completed_sections": row["completed_sections"], "failed_sections": row["failed_sections"],
        "current_part_id": row["current_part_id"], "message": row["message"],
        "error_message": row["error_message"], "started_at": row["started_at"].isoformat(),
        "model": row.get("model"),
        "cancel_requested": row.get("cancel_requested", False),
        "can_resume": row["status"] in {"failed", "cancelled", "completed_with_errors"} and bool(row.get("input_snapshot")),
        "preserved_sections": len(row.get("resume_part_ids") or []),
        "resumed_from_run_id": str(row["resumed_from_run_id"]) if row.get("resumed_from_run_id") else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }


def serialize_report_export(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "progress": row["progress"],
        "stage": row["stage"], "message": row["message"], "error_message": row["error_message"],
        "file_name": row["file_name"], "validation": row["validation"],
        "download_url": f"/api/v2/report/exports/{row['id']}/download" if row["status"] == "completed" else None,
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }


def serialize_presentation_export(row: dict) -> dict:
    return {
        "id": str(row["id"]), "status": row["status"], "progress": row["progress"],
        "stage": row["stage"], "message": row["message"], "error_message": row["error_message"],
        "file_name": row["file_name"], "model": row["model"], "slide_count": row.get("slide_count") or (row.get("validation") or {}).get("slide_count") or SLIDE_COUNT,
        "validation": row["validation"],
        "download_url": f"/api/v2/report/presentations/{row['id']}/download" if row["status"] == "completed" else None,
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
    }
