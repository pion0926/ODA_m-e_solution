from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi.encoders import jsonable_encoder

from .db import connection
from .openrouter import redact_for_external_analysis
from .report_exporter import _pipeline_context
from .report_sections import section_documents
from .report_text import sanitize_report_text


def _short(value: Any, limit: int) -> str:
    text = sanitize_report_text(str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _analysis_excerpt(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, (dict, list)):
        return _short(json.dumps(jsonable_encoder(value), ensure_ascii=False), 1800)
    return _short(value, 1800)


def _evidence_catalog(section_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    catalog: dict[str, dict[str, Any]] = {}
    section_map: dict[str, list[str]] = {}
    usage: defaultdict[str, list[str]] = defaultdict(list)
    for row in section_rows:
        part_id = str(row["part_id"])
        documents = section_documents(part_id)
        names: list[str] = []
        for document in documents:
            document_id = str(document.get("id") or "")
            file_name = str(document.get("original_name") or "근거자료")
            names.append(file_name)
            usage[document_id].append(part_id)
            if document_id not in catalog:
                catalog[document_id] = {
                    "document_id": document_id,
                    "file_name": file_name,
                    "summary": _short(document.get("summary"), 1200),
                    "analysis_excerpt": _analysis_excerpt(document.get("analysis")),
                    "matched_via": document.get("matched_via"),
                    "matched_criterion": document.get("matched_criterion"),
                    "matched_slot": document.get("matched_slot_title"),
                    "confidence": document.get("confidence"),
                    "authoritative_pdm": bool(document.get("is_authoritative_pdm")),
                }
        section_map[part_id] = list(dict.fromkeys(names))
    for document_id, item in catalog.items():
        item["used_by_sections"] = list(dict.fromkeys(usage[document_id]))
    items = list(catalog.values())
    items.sort(key=lambda item: (not item["authoritative_pdm"], -(float(item.get("confidence") or 0)), item["file_name"]))
    return items[:60], section_map


def collect_presentation_source() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Collect the saved pre-HWPX report plus traceable project evidence."""
    context, _sections, conversion = _pipeline_context()
    with connection() as conn:
        rows = conn.execute(
            """SELECT section_number,part_id,title,content,source_document_ids,
                      generation_model,generation_metadata,quality_score,quality_report
                 FROM report_sections ORDER BY section_number"""
        ).fetchall()
        pdm_row = conn.execute(
            "SELECT source_file_name,pdm_version,model,created_at FROM pdm_models ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        run = conn.execute(
            "SELECT id,model,document_count,completed_at FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        evaluations = conn.execute(
            """SELECT criterion_id,criterion_name,score,summary,score_reason,
                      question_assessments,evidence_gaps,source_document_count
                 FROM criterion_evaluations WHERE run_id=%s ORDER BY id""",
            (run["id"],),
        ).fetchall() if run else []

    if len(rows) != 27:
        raise RuntimeError(f"발표자료의 원문이 되는 보고서 섹션이 27개가 아닙니다: {len(rows)}개")

    report_sections: list[dict[str, Any]] = []
    for row in rows:
        content = sanitize_report_text(row["content"])
        if not content.strip():
            raise RuntimeError(f"발표자료 생성 전 보고서 섹션이 비어 있습니다: {row['title']}")
        report_sections.append({
            "section_number": row["section_number"],
            "part_id": row["part_id"],
            "title": row["title"],
            "content": content,
            "source_document_ids": row.get("source_document_ids") or [],
            "generation_model": row.get("generation_model"),
            "quality_score": float(row["quality_score"]) if row.get("quality_score") is not None else None,
        })

    evidence_catalog, section_evidence = _evidence_catalog(rows)
    # Keep internal identifiers local. External text redaction may replace
    # digit sequences inside UUIDs; redacted strings must never drive SQL.
    context["presentation_photo_document_ids"] = [d["document_id"] for d in evidence_catalog if d.get("document_id")]
    for item in report_sections:
        item["evidence_files"] = section_evidence.get(str(item["part_id"]), [])

    summary = {
        "project": context["project"],
        "overall": context["overall"],
        "criteria": [{
            "id": item.get("id"),
            "name": item.get("name"),
            "score": item.get("currentScore4"),
            "summary": (item.get("evaluationResult") or {}).get("summary"),
            "rationale": (item.get("evaluationResult") or {}).get("rationale"),
        } for item in context.get("criteria", [])],
        "pdm_source": context.get("_pdm_source_name"),
    }
    structured_evidence = {
        "pdm": {
            "source_file_name": pdm_row.get("source_file_name") if pdm_row else None,
            "version": pdm_row.get("pdm_version") if pdm_row else None,
            "model": pdm_row.get("model") if pdm_row else None,
        },
        "evaluation_run": {
            "model": run.get("model") if run else None,
            "document_count": run.get("document_count") if run else 0,
            "completed_at": run.get("completed_at") if run else None,
            "criteria": evaluations,
        },
        "hwpx_conversion_contract": conversion,
    }
    payload = jsonable_encoder({
        "summary": summary,
        "report_sections": report_sections,
        "structured_evidence": structured_evidence,
        "evidence_catalog": evidence_catalog,
    })
    redacted_text, sensitive_flags = redact_for_external_analysis(
        json.dumps(payload, ensure_ascii=False)
    )
    return context, json.loads(redacted_text), sensitive_flags
