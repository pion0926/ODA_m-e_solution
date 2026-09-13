from __future__ import annotations

from ..core import *
from ..documents.evidence_store import list_uploaded_documents
from ..documents.text_extraction import read_reference_text_full, truncate_reference_text
from ..reports.context import CRITERION_LABELS, criterion_label, report_criteria
from ..utils.common import find_criterion


def criteria_for_report_part(part_id: str, part: dict | None = None) -> list[str]:
    if isinstance(part, dict) and isinstance(part.get("referenceCriteria"), list):
        return list(part.get("referenceCriteria") or [])
    if part_id == "criteria-relevance":
        return ["relevance"]
    if part_id == "criteria-coherence":
        return ["coherence"]
    if part_id == "criteria-effectiveness":
        return ["effectiveness"]
    if part_id == "criteria-efficiency":
        return ["efficiency"]
    if part_id == "criteria-sustainability":
        return ["sustainability"]
    if part_id in {
        "criteria-crosscutting",
        "criteria-other",
        "grade",
        "conclusion",
        "working-factors",
        "nonworking-factors",
        "theory",
        "feedback",
        "lessons",
        "achievement",
    }:
        return [criterion["id"] for criterion in report_criteria()]
    return []

def all_reference_documents_for_criteria(criteria_ids: list[str]) -> list[dict]:
    seen = set()
    documents = []
    for criterion_id in criteria_ids:
        for document in list_uploaded_documents(criterion_id):
            key = (document.get("id"), document.get("rawPath"), document.get("fileName"), criterion_id)
            if key in seen:
                continue
            seen.add(key)
            documents.append((criterion_id, document))
    documents.sort(key=lambda item: (
        str(item[0]),
        str(item[1].get("evidenceName") or ""),
        str(item[1].get("uploadedAt") or ""),
        str(item[1].get("fileName") or ""),
    ))
    return [{"criterionId": criterion_id, **document} for criterion_id, document in documents]


def build_evaluation_reference_corpus(criterion_id: str) -> dict:
    """Build a long-form source corpus for criterion scoring."""
    criterion = find_criterion(criterion_id) or {}
    documents = []
    used_chars = 0
    for index, document in enumerate(list_uploaded_documents(criterion_id), start=1):
        if used_chars >= EVALUATION_REFERENCE_CHAR_BUDGET:
            break
        remaining = EVALUATION_REFERENCE_CHAR_BUDGET - used_chars
        limit = min(EVALUATION_REFERENCE_DOC_CHAR_LIMIT, remaining)
        full = read_reference_text_full(document)
        text, truncated = truncate_reference_text(str(full.get("text") or ""), limit)
        if not text:
            continue
        used_chars += len(text)
        documents.append({
            "referenceNumber": document.get("referenceNumber") or index,
            "criterionId": criterion_id,
            "criterionName": criterion_label(criterion),
            "fileName": document.get("fileName", ""),
            "evidenceName": document.get("evidenceName", ""),
            "quality": full.get("quality", ""),
            "extractionMethod": full.get("method", ""),
            "originalCharCount": full.get("charCount", 0),
            "includedCharCount": len(text),
            "truncated": truncated,
            "text": text,
        })
    return {
        "policy": (
            "점수 평가 전용 원문 코퍼스입니다. 해당 평가기준에 배정된 문서만 포함하며, "
            "각 문서의 evidenceName과 fileName을 근거 맥락으로 사용하세요."
        ),
        "charBudget": EVALUATION_REFERENCE_CHAR_BUDGET,
        "docCharLimit": EVALUATION_REFERENCE_DOC_CHAR_LIMIT,
        "usedChars": used_chars,
        "documentCount": len(documents),
        "documents": documents,
    }


def limited_reference_document_score(part_id: str, document: dict) -> int:
    keywords = REPORT_LIMITED_REFERENCE_KEYWORDS.get(part_id, ())
    if not keywords:
        return 0
    haystack = " ".join(
        str(document.get(key) or "")
        for key in ("fileName", "evidenceName", "criterionName", "category")
    ).lower()
    score = 0
    for keyword in keywords:
        if str(keyword).lower() in haystack:
            score += 3
    evidence_name = str(document.get("evidenceName") or "")
    if any(token in evidence_name for token in ("조사", "인터뷰", "면담", "현장", "PDM", "성과지표")):
        score += 2
    if any(token in str(document.get("fileName") or "") for token in ("인터뷰", "조사", "Survey", "survey", "PDM", "성과")):
        score += 2
    return score


def limit_reference_documents_for_part(part_id: str, documents: list[dict]) -> list[dict]:
    limit = REPORT_LIMITED_REFERENCE_PART_LIMITS.get(part_id)
    if not limit or len(documents) <= limit:
        return documents
    ranked = [
        (limited_reference_document_score(part_id, document), index, document)
        for index, document in enumerate(documents)
    ]
    matched = [item for item in ranked if item[0] > 0]
    selected = matched if len(matched) >= max(1, limit // 2) else ranked
    selected.sort(key=lambda item: (-item[0], str(item[2].get("criterionId") or ""), str(item[2].get("evidenceName") or ""), item[1]))
    return [document for _score, _index, document in selected[:limit]]


def assigned_reference_documents_for_part(part: dict) -> list[dict]:
    """Return only documents assigned to this report part's evidence slots."""
    part_id = str(part.get("id") or "")
    custom_ids = {str(value) for value in part.get("customReferenceDocumentIds", []) if str(value)}
    if custom_ids:
        selected = []
        for criterion_id in ("relevance", "coherence", "effectiveness", "efficiency", "sustainability", "impact"):
            for document in list_uploaded_documents(criterion_id):
                if str(document.get("id") or "") in custom_ids:
                    selected.append({"criterionId": criterion_id, **document})
        selected.sort(key=lambda item: (str(item.get("criterionId")), str(item.get("evidenceName")), str(item.get("fileName"))))
        return selected
    reference_evidence = part.get("referenceEvidence", {}) if isinstance(part.get("referenceEvidence"), dict) else {}
    criteria_ids = criteria_for_report_part(part_id, part)
    seen = set()
    documents = []
    for criterion_id in criteria_ids:
        allowed = [str(item) for item in reference_evidence.get(criterion_id, []) if str(item).strip()]
        allowed_set = set(allowed)
        for document in list_uploaded_documents(criterion_id):
            evidence_name = str(document.get("evidenceName") or "")
            if allowed_set and evidence_name not in allowed_set:
                continue
            key = (document.get("id"), document.get("rawPath"), document.get("fileName"), criterion_id, evidence_name)
            if key in seen:
                continue
            seen.add(key)
            documents.append((criterion_id, document))
    documents.sort(key=lambda item: (
        str(item[0]),
        str(item[1].get("evidenceName") or ""),
        str(item[1].get("uploadedAt") or ""),
        str(item[1].get("fileName") or ""),
    ))
    assigned = [{"criterionId": criterion_id, **document} for criterion_id, document in documents]
    return limit_reference_documents_for_part(part_id, assigned)


def build_full_reference_corpus(part: dict) -> dict:
    part_id = str(part.get("id") or "")
    if not REPORT_FULL_REFERENCE_ENABLED:
        return {"enabled": False, "reason": "REPORT_FULL_REFERENCE_ENABLED=0"}
    if part_id in REPORT_FULL_REFERENCE_DISABLED_PARTS:
        return {
            "enabled": True,
            "partId": part_id,
            "criteria": criteria_for_report_part(part_id, part),
            "documents": [],
            "omittedDocuments": [],
            "instructions": (
                "이 파트는 원문 문서 전체를 다시 투입하지 않는다. "
                "앞서 작성된 분석 섹션, 기준별 평가결과, 등급표 요약을 1차 근거로 종합한다."
            ),
        }
    criteria_ids = criteria_for_report_part(part_id, part)
    reference_evidence = part.get("referenceEvidence", {}) if isinstance(part.get("referenceEvidence"), dict) else {}
    if not criteria_ids:
        return {"enabled": True, "documents": [], "instructions": "이 파트는 기준별 업로드 문서보다 사업 기본정보와 샘플 양식을 우선 사용한다."}
    raw_documents = assigned_reference_documents_for_part(part)
    remaining_budget = REPORT_FULL_REFERENCE_CHAR_BUDGET
    documents = []
    omitted = []
    for index, document in enumerate(raw_documents, start=1):
        full = read_reference_text_full(document)
        source_text = full.get("text", "")
        if remaining_budget <= 0:
            omitted.append({
                "criterionId": document.get("criterionId"),
                "fileName": document.get("fileName", ""),
                "reason": "fullReferenceCorpus char budget exhausted",
            })
            continue
        per_doc_limit = min(REPORT_FULL_REFERENCE_DOC_CHAR_LIMIT, remaining_budget)
        text, truncated = truncate_reference_text(source_text, per_doc_limit)
        remaining_budget -= len(text)
        documents.append({
            "docNo": index,
            "criterionId": document.get("criterionId"),
            "criterionName": CRITERION_LABELS.get(str(document.get("criterionId")), str(document.get("criterionId"))),
            "evidenceName": document.get("evidenceName", ""),
            "fileName": document.get("fileName", ""),
            "uploadedAt": document.get("uploadedAt", ""),
            "extraction": {
                "method": full.get("method"),
                "quality": full.get("quality"),
                "charCount": full.get("charCount"),
                "includedChars": len(text),
                "truncated": truncated,
                "note": "quality가 ocr_required/low이면 원문 파일은 있으나 텍스트 추출 신뢰도가 낮으므로 보수적으로 사용",
            },
            "text": text,
        })
    return {
        "enabled": True,
        "partId": part_id,
        "criteria": criteria_ids,
        "evidenceSlots": reference_evidence,
        "budget": {
            "maxChars": REPORT_FULL_REFERENCE_CHAR_BUDGET,
            "remainingChars": remaining_budget,
            "perDocumentMaxChars": REPORT_FULL_REFERENCE_DOC_CHAR_LIMIT,
        },
        "instructions": (
            "아래 documents는 이 보고서 파트에 사전 할당된 evidence 슬롯과 일치하는 원문 코퍼스이다. "
            "각 문서의 criterionId, evidenceName, fileName을 근거 맥락으로 사용한다. "
            "텍스트를 그대로 복사하지 말고 현재 섹션 목적에 맞게 종합한다. "
            "quality가 usable인 문서는 적극 활용하고, low/ocr_required 문서는 파일 존재와 제한적 키워드만 확인된 것으로 취급한다. "
            "문서에 근거가 있으면 '자료 기반 보수 작성'를 남기지 않는다."
        ),
        "documents": documents,
        "omittedDocuments": omitted,
    }

