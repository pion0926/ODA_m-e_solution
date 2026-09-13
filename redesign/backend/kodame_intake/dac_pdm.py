"""Capture the PDM state used by a DAC run, including source references."""
from __future__ import annotations

from .db import connection
from .pdm_monitoring import refresh_pdm_model


def build_context(row, assignments, documents):
    model = row["model"]
    source_ids = {str(row["source_document_id"])}
    if model.get("performance_source_document_id"):
        source_ids.add(str(model["performance_source_document_id"]))
    for item in assignments:
        source_ids.add(str(item["document_id"]))
    for indicator in model.get("performance_indicators", []):
        source_ids.update(str(value) for value in indicator.get("evidence_document_ids", []))
        source_ids.update(str(value["document_id"]) for value in indicator.get("measurement_sources", []))
    refs = {doc["ref"]: doc["id"] for doc in documents if doc["id"] in source_ids}
    return {
        "status": "completed",
        "snapshot_id": str(row["id"]),
        "created_at": row["created_at"].isoformat(),
        "source_document_id": str(row["source_document_id"]),
        "source_file_name": row["source_file_name"],
        "model": model,
        "document_assignments": [{**item, "document_id": str(item["document_id"]),
                                  "confidence": float(item["confidence"])} for item in assignments],
        "evidence_document_refs": refs,
    }


def refresh_context(documents):
    if not any("pdm" in doc["name"].lower() and doc["name"].lower().endswith(".pdf") for doc in documents):
        return {"status": "unavailable", "reason": "분석 가능한 PDM 원본 PDF가 업로드되지 않았습니다.",
                "model": {}, "evidence_document_refs": {}}
    model_id = refresh_pdm_model(analyze_risks=True)
    with connection() as conn:
        row = conn.execute("SELECT * FROM pdm_models WHERE id=%s", (model_id,)).fetchone()
        if not row:
            raise RuntimeError("PDM이 동시에 갱신되었습니다. DAC 재평가를 다시 실행하세요.")
        assignments = conn.execute(
            "SELECT document_id,indicator_id,tier,requirement_title,confidence,rationale FROM pdm_document_assignments"
        ).fetchall()
    return build_context(row, assignments, documents)


def attach_question_context(question, pdm_context):
    """Persist exactly what the evaluator considered, without converting rates into scores."""
    indicators = pdm_context.get("model", {}).get("performance_indicators", [])
    valid_ids = {item["id"] for item in indicators}
    selected = question.get("pdm_indicator_ids", [])
    if not isinstance(selected, list) or any(value not in valid_ids for value in selected):
        raise RuntimeError("DAC 평가의 PDM 지표 참조가 유효하지 않습니다.")
    question["pdm_context"] = {
        "status": pdm_context["status"], "snapshot_id": pdm_context.get("snapshot_id"),
        "indicator_count": len(indicators), "used_indicator_ids": selected,
    }
    for indicator in indicators:
        if indicator["id"] not in selected:
            continue
        for source in indicator.get("measurement_sources", []):
            quote = {"document_id": source["document_id"], "file_name": source["file_name"],
                     "quote": source["quote"], "finding": f"{indicator['indicator']}: {source['value']}",
                     "question_id": question["question_id"], "pdm_indicator_id": indicator["id"]}
            if quote not in question["evidence_quotes"]:
                question["evidence_quotes"].append(quote)
            if source["document_id"] not in question["evidence_document_ids"]:
                question["evidence_document_ids"].append(source["document_id"])
