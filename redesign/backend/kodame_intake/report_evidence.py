from __future__ import annotations

import re
from pathlib import Path

from .openrouter import redact_for_external_analysis
from .report_references import SECTION_GUIDANCE
from .report_sources import is_report_evidence_document, normalize_source_mentions, reader_source_label


_PAGE_MARKER_RE = re.compile(r"(?m)^\s*-\s*(\d{1,4})\s*-\s*$")


def _chunks(text: str, size: int = 3200, overlap: int = 350) -> list[str]:
    text = re.sub(r"\x00", " ", text or "")
    text = re.sub(r"\n{4,}", "\n\n", text)
    if len(text) <= size:
        return [text.strip()] if text.strip() else []
    result: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            result.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return result


def _score(part_id: str, document: dict, chunk: str) -> float:
    guide = SECTION_GUIDANCE[part_id]
    searchable = f"{document.get('original_name', '')}\n{document.get('summary', '')}\n{document.get('rationale', '')}\n{chunk}".lower()
    score = float(document.get("confidence") or 0.5) * 12
    for keyword in guide["keywords"]:
        count = searchable.count(keyword.lower())
        score += min(count, 6) * 3.5
    analysis = document.get("analysis") if isinstance(document.get("analysis"), dict) else {}
    doc_type = str(analysis.get("document_type") or "")
    if any(token in doc_type for token in ("보고서", "계획서", "통계", "정책", "재무")):
        score += 3
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|명|건|원|달러|개월|년)", chunk):
        score += 4
    if document.get("is_authoritative_pdm"):
        # A PDM revision defines the indicator roster and hierarchy.  It must
        # be visible to PDM/achievement generation before older plans whose
        # keyword density would otherwise give them a higher retrieval score.
        score += 1000 if part_id in {"pdm", "achievement"} else 80
    return score


def _source_location(chunk: str, chunk_index: int) -> str:
    pages = [int(match.group(1)) for match in _PAGE_MARKER_RE.finditer(chunk)]
    if pages:
        first, last = min(pages), max(pages)
        return f"p.{first}" if first == last else f"pp.{first}-{last}"
    # Non-PDF sources (spreadsheets, text files) usually have no physical page
    # marker.  Expose a stable item locator instead of encouraging the model
    # to invent a page number.
    return f"추출 항목 {chunk_index + 1}"


def evidence_packet(part_id: str, documents: list[dict], limit: int = 12) -> list[dict]:
    candidates: list[tuple[float, int, int, str]] = []
    for doc_index, document in enumerate(documents):
        if not is_report_evidence_document(document.get("original_name"), document.get("analysis")):
            continue
        path_value = document.get("extracted_path")
        if not path_value:
            continue
        path = Path(path_value)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk_index, chunk in enumerate(_chunks(text)):
            candidates.append((_score(part_id, document, chunk), doc_index, chunk_index, chunk))
    candidates.sort(reverse=True, key=lambda item: item[0])
    selected: list[dict] = []
    per_document: dict[int, int] = {}
    for score, doc_index, chunk_index, chunk in candidates:
        if per_document.get(doc_index, 0) >= 2:
            continue
        document = documents[doc_index]
        redacted, _ = redact_for_external_analysis(chunk[:3000])
        source_name = str(document.get("original_name") or "")
        evidence_id = f"E{len(selected) + 1:02d}"
        selected.append({
            "evidence_id": evidence_id,
            "document_id": str(document["id"]),
            "source_label": reader_source_label(source_name, document.get("analysis")),
            "document_summary": normalize_source_mentions(document.get("summary") or "", [source_name])[:800],
            "assignment_reason": normalize_source_mentions(document.get("rationale") or "", [source_name])[:500],
            "excerpt": normalize_source_mentions(redacted, [source_name]),
            "retrieval_score": round(score, 2),
            "chunk_index": chunk_index,
            "source_location": _source_location(chunk, chunk_index),
            "source_role": "최신 승인 PDM" if document.get("is_authoritative_pdm") else "근거자료",
        })
        per_document[doc_index] = per_document.get(doc_index, 0) + 1
        if len(selected) >= limit:
            break
    return selected
