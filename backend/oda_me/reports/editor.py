from __future__ import annotations

from ..core import *
from ..clients.openrouter import OPENROUTER
from ..documents.evidence_store import evaluation_path, list_uploaded_documents, load_evaluation_result
from ..documents.reference_corpus import (
    assigned_reference_documents_for_part,
    build_full_reference_corpus,
    limit_reference_documents_for_part,
)
from ..documents.text_extraction import read_reference_text_full
from ..hwpx.formatting import (
    criterion_grade_rows,
    enforce_editor_part_content,
    markdown_table_to_report_text,
    polish_report_sections_for_final,
)
from ..utils.common import now_label
from .context import (
    CRITERIA_REPORT_PART_IDS,
    CRITERION_LABELS,
    editor_part_output_contract,
    sanitize_editor_part_response,
    structured_slots_to_json,
    strip_editor_part_headings,
)
from .export_builders import complete_report_sections, current_report_context, fallback_report_blueprint
from .section_settings import editor_report_parts


SAMPLE_REFERENCE_USAGE_PROMPT = """

[좋은 샘플 활용 규칙]
- sample_reference_for_this_section은 사용자가 제공한 잘 작성된 실제 보고서 예시다.
- 샘플의 구조, 항목 분리 방식, 논리 전개, 공적 보고서 문체, 근거 밀도를 우선 참고한다.
- 샘플의 사업명, 고유 사실, 수치, 평가 판단, 문장을 복사하거나 현재 사업 사실처럼 쓰지 않는다.
- 현재 섹션의 자료가 충분하면 샘플 수준의 완성된 본문으로 작성하고, 단순 점수 메모나 표 원문 요약으로 끝내지 않는다.
""".strip()


def find_editor_criterion(criterion_id: str) -> dict | None:
    return next((item for item in CRITERIA if item.get("id") == criterion_id), None)


ENABLED_EDITOR_PART_IDS = {
    "cover",
    "toc",
    "notice",
    "grade",
    "summary-ko",
    "project-background",
    "project-overview",
    "pdm",
    "eval-purpose",
    "eval-matrix",
    "eval-methods",
    "eval-limitations",
    "eval-team",
    "achievement",
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
    "theory",
    "feedback",
    "lessons",
}
ENABLED_EDITOR_SECTION_IDS = {
    "title",
    "toc",
    "notice",
    "grade",
    "summary",
    "project-background",
    "project-overview",
    "pdm",
    "eval-purpose",
    "eval-matrix",
    "eval-methods",
    "eval-limitations",
    "eval-team",
    "achievement",
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
    "theory",
    "feedback",
    "lessons",
}


DETAILED_EVIDENCE_WRITING_PART_IDS = {
    "summary-ko",
    "project-background",
    "eval-purpose",
    "eval-methods",
    "eval-limitations",
    "eval-team",
    "achievement",
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
    "theory",
    "feedback",
    "lessons",
}


def is_enabled_editor_item(section: dict | None) -> bool:
    if not isinstance(section, dict):
        return False
    value = str(section.get("id") or section.get("sectionId") or "")
    return value in ENABLED_EDITOR_PART_IDS or value in ENABLED_EDITOR_SECTION_IDS


def prompt_with_sample_reference_usage(prompt: object) -> str:
    base = str(prompt or "").strip()
    if SAMPLE_REFERENCE_USAGE_PROMPT in base:
        return base
    return (base + "\n\n" + SAMPLE_REFERENCE_USAGE_PROMPT).strip()


def report_editor_sections(context: dict, blueprint: dict) -> list[dict]:
    return complete_report_sections(context, blueprint, use_saved=False)


def read_report_editor_state() -> dict | None:
    if not REPORT_EDITOR_STATE_PATH.exists():
        return None
    try:
        return json.loads(REPORT_EDITOR_STATE_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def file_signature(path_value: str | None) -> dict:
    if not path_value:
        return {}
    path = Path(path_value)
    try:
        stat = path.stat()
    except OSError:
        return {"name": path.name, "missing": True}
    return {
        "name": path.name,
        "size": stat.st_size,
        "mtime": round(stat.st_mtime, 3),
    }


def project_overview_signature() -> dict:
    overview = current_project_overview()
    overview_name = Path(str(overview.get("name") or "")).name
    return {
        "kind": "project_overview",
        "name": overview_name,
        "source": overview.get("source"),
        "title": overview.get("projectTitle"),
        "period": overview.get("projectPeriod"),
        "budget": overview.get("projectBudget"),
        "updatedAt": overview.get("uploadedAt") or overview.get("updatedAt"),
        "raw": file_signature(overview.get("path")),
        "text": file_signature(overview.get("textPath")),
    }


def criterion_document_signatures(criterion_ids: list[str], evidence_filter: dict[str, list[str]] | None = None) -> list[dict]:
    signatures = []
    for criterion_id in criterion_ids:
        criterion = find_editor_criterion(criterion_id) or {"evidence": []}
        documents = list_uploaded_documents(criterion_id)
        allowed_evidence = set((evidence_filter or {}).get(criterion_id) or [])
        for document in documents:
            evidence_name = str(document.get("evidenceName") or "")
            if allowed_evidence and evidence_name not in allowed_evidence:
                continue
            signatures.append({
                "kind": "uploaded_document",
                "criterionId": criterion_id,
                "id": document.get("id"),
                "evidenceName": evidence_name,
                "fileName": document.get("fileName"),
                "size": document.get("size"),
                "uploadedAt": document.get("uploadedAt"),
                "raw": file_signature(document.get("rawPath")),
                "text": file_signature(document.get("textPath")),
            })
        signatures.append({
            "kind": "required_evidence_list",
            "criterionId": criterion_id,
            "items": [
                {
                    "category": item.get("category", ""),
                    "name": item.get("name", ""),
                }
                for item in criterion.get("evidence", [])
                if not allowed_evidence or item.get("name", "") in allowed_evidence
            ],
        })
        eval_path = evaluation_path(criterion_id)
        signatures.append({
            "kind": "criterion_evaluation",
            "criterionId": criterion_id,
            "file": file_signature(str(eval_path)),
        })
    return signatures


def full_reference_corpus_signature(part: dict) -> dict:
    part_id = str(part.get("id") or "")
    if part_id in REPORT_FULL_REFERENCE_DISABLED_PARTS:
        return {
            "enabled": REPORT_FULL_REFERENCE_ENABLED,
            "disabledForPart": True,
            "reason": "summary/conclusion parts synthesize prior section analysis instead of rereading source corpus",
            "criteria": related_criteria_for_part(part_id),
            "documentCount": 0,
            "totalChars": 0,
            "qualityCounts": {},
            "items": [],
        }
    documents = assigned_reference_documents_for_part(part)
    items = []
    quality_counts: dict[str, int] = {}
    total_chars = 0
    for document in documents:
        full = read_reference_text_full(document)
        quality = str(full.get("quality") or "unknown")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        total_chars += int(full.get("charCount") or 0)
        items.append({
            "criterionId": document.get("criterionId"),
            "id": document.get("id"),
            "fileName": document.get("fileName"),
            "evidenceName": document.get("evidenceName"),
            "method": full.get("method"),
            "quality": quality,
            "charCount": full.get("charCount"),
            "raw": file_signature(document.get("rawPath")),
            "text": file_signature(document.get("textPath")),
        })
    return {
        "enabled": REPORT_FULL_REFERENCE_ENABLED,
        "budget": REPORT_FULL_REFERENCE_CHAR_BUDGET,
        "perDocumentLimit": REPORT_FULL_REFERENCE_DOC_CHAR_LIMIT,
        "documentCount": len(items),
        "criteria": related_criteria_for_part(str(part.get("id") or "")),
        "evidenceSlots": part.get("referenceEvidence", {}) if isinstance(part.get("referenceEvidence"), dict) else {},
        "totalChars": total_chars,
        "qualityCounts": quality_counts,
        "items": items,
    }


def related_criteria_for_part(part_id: str) -> list[str]:
    part = next((item for item in editor_report_parts() if item.get("id") == part_id), None)
    if part and isinstance(part.get("referenceCriteria"), list):
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
    if part_id in {"criteria-crosscutting", "criteria-other", "grade", "conclusion", "working-factors", "nonworking-factors", "theory", "feedback", "lessons", "achievement"}:
        return [criterion["id"] for criterion in report_criteria()]
    return []


def part_related_sources(part: dict) -> dict:
    part_id = str(part.get("id"))
    project_related = {
        "cover",
        "toc",
        "notice",
        "project-background",
        "project-overview",
        "pdm",
        "eval-purpose",
        "eval-matrix",
        "eval-methods",
        "eval-limitations",
        "eval-team",
        "achievement",
        "grade",
        "summary-ko",
        "conclusion",
        "working-factors",
        "nonworking-factors",
        "theory",
        "feedback",
        "lessons",
    }
    criteria_ids = related_criteria_for_part(part_id)
    reference_evidence = part.get("referenceEvidence", {}) if isinstance(part.get("referenceEvidence"), dict) else {}
    sources = {
        "partId": part_id,
        "sectionId": part.get("sectionId") or part_id,
        "prompt": part.get("prompt", ""),
        "requiredInputs": part.get("requiredInputs", []),
        "referenceCriteria": criteria_ids,
        "referenceEvidence": reference_evidence,
        "referenceNotes": part.get("referenceNotes", []),
        "generatorVersion": REPORT_GENERATOR_VERSION,
        "projectOverview": project_overview_signature() if part_id in project_related else None,
        "criteriaDocuments": criterion_document_signatures(criteria_ids, reference_evidence),
        "fullReferenceCorpus": full_reference_corpus_signature(part) if criteria_ids else None,
    }
    return sources


def part_fingerprint(part: dict) -> str:
    payload = json.dumps(part_related_sources(part), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prior_analysis_sections_for_part(part_id: str, sections: list[dict], current_section_id: str = "") -> list[dict]:
    if part_id not in REPORT_FULL_REFERENCE_DISABLED_PARTS and part_id not in REPORT_LIMITED_REFERENCE_PART_LIMITS:
        return []
    saved_state = read_report_editor_state() or {}
    combined: dict[str, dict] = {}
    for section in saved_state.get("sections", []):
        if isinstance(section, dict) and section.get("id"):
            combined[str(section.get("id"))] = section
    for section in sections:
        if isinstance(section, dict) and section.get("id"):
            combined[str(section.get("id"))] = section

    preferred_by_part = {
        "grade": ["criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability"],
        "summary-ko": ["project-overview", "pdm", "eval-purpose", "eval-methods", "eval-limitations", "achievement", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability", "conclusion", "feedback", "lessons"],
        "eval-matrix": ["eval-purpose", "project-overview", "pdm"],
        "eval-methods": ["eval-purpose", "eval-matrix"],
        "eval-limitations": ["eval-methods", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability"],
        "criteria-other": ["criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability", "achievement"],
        "conclusion": ["achievement", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability", "criteria-crosscutting", "criteria-other"],
        "working-factors": ["achievement", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability", "conclusion"],
        "nonworking-factors": ["achievement", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability", "conclusion"],
        "feedback": ["conclusion", "working-factors", "nonworking-factors", "theory", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability"],
        "lessons": ["conclusion", "working-factors", "nonworking-factors", "feedback", "theory", "criteria-relevance", "criteria-coherence", "criteria-effectiveness", "criteria-efficiency", "criteria-sustainability"],
    }
    section_ids = preferred_by_part.get(part_id, [])
    output = []
    for section_id in section_ids:
        if section_id == current_section_id:
            continue
        section = combined.get(section_id)
        body = str((section or {}).get("body") or "").strip()
        if not body:
            continue
        title = str((section or {}).get("title") or section_id)
        output.append({
            "id": section_id,
            "title": title,
            "body": short_text(strip_editor_part_headings(body, section_id), 3500),
        })
    return output


def part_reference_documents(part: dict) -> dict:
    reference_evidence = part.get("referenceEvidence", {}) if isinstance(part.get("referenceEvidence"), dict) else {}
    criteria_ids = related_criteria_for_part(str(part.get("id")))
    broad_parts = {
        "grade",
        "summary-ko",
        "eval-matrix",
        "eval-methods",
        "eval-limitations",
        "conclusion",
        "working-factors",
        "nonworking-factors",
        "feedback",
        "lessons",
        "criteria-other",
    }
    strict_parts = {"cover", "project-overview", "pdm", "achievement"}
    part_id = str(part.get("id") or "")
    max_total_documents = 14 if part_id in broad_parts else 10
    max_documents_per_criterion = 3 if part_id in broad_parts else 8
    uploaded = []
    missing = []
    for criterion_id in criteria_ids:
        allowed = list(reference_evidence.get(criterion_id) or [])
        allowed_set = set(allowed)
        documents = list_uploaded_documents(criterion_id)
        exact_documents = []
        supplemental_documents = []
        matched_names = set()
        for document in documents:
            evidence_name = str(document.get("evidenceName") or "")
            exact_match = not allowed_set or evidence_name in allowed_set
            if exact_match:
                matched_names.add(evidence_name)
                exact_documents.append(document)
            else:
                supplemental_documents.append(document)
        selected_documents = exact_documents[:max_documents_per_criterion]
        remaining_slots = max(0, max_documents_per_criterion - len(selected_documents))
        if remaining_slots:
            selected_documents.extend(supplemental_documents[:remaining_slots])
        for document in selected_documents:
            if len(uploaded) >= max_total_documents:
                break
            evidence_name = str(document.get("evidenceName") or "")
            text_excerpt = ""
            text_path = document.get("textPath")
            if text_path and Path(text_path).exists():
                excerpt_limit = 2200 if part_id not in broad_parts else 1400
                text_excerpt = Path(text_path).read_text(encoding="utf-8", errors="replace")[:excerpt_limit]
            uploaded.append({
                "criterionId": criterion_id,
                "criterionName": CRITERION_LABELS.get(criterion_id, criterion_id),
                "evidenceName": evidence_name,
                "fileName": document.get("fileName", ""),
                "uploadedAt": document.get("uploadedAt", ""),
                "textExcerpt": text_excerpt,
                "match": "direct" if (not allowed_set or evidence_name in allowed_set) else "supporting",
            })
        evaluation = load_evaluation_result(criterion_id) or {}
        has_evaluation = bool(evaluation.get("score") or evaluation.get("summary") or evaluation.get("sections"))
        has_sufficient_alternative = bool(exact_documents or supplemental_documents or has_evaluation)
        if part_id in strict_parts:
            has_sufficient_alternative = bool(exact_documents or (part_id == "cover" and project_overview_signature().get("title")))
        if allowed and not has_sufficient_alternative:
            for evidence_name in allowed[:4]:
                missing.append({
                    "criterionId": criterion_id,
                    "criterionName": CRITERION_LABELS.get(criterion_id, criterion_id),
                    "evidenceName": evidence_name,
                    "message": f"자동 초안 생성 제약: {evidence_name}",
                })
        elif allowed and part_id in strict_parts and not exact_documents:
            missing.append({
                "criterionId": criterion_id,
                "criterionName": CRITERION_LABELS.get(criterion_id, criterion_id),
                "evidenceName": allowed[0],
                "message": f"자동 초안 생성 제약: {allowed[0]} 전용 슬롯 또는 이를 대체할 명확한 원문",
            })
    if part_id in REPORT_LIMITED_REFERENCE_PART_LIMITS:
        uploaded = limit_reference_documents_for_part(part_id, uploaded)
    return {
        "criteria": criteria_ids,
        "requiredEvidence": reference_evidence,
        "uploadedDocuments": uploaded,
        "missingEvidence": missing,
        "notes": part.get("referenceNotes", []),
    }


def report_editor_state_sections_map(saved: dict | None) -> dict[str, dict]:
    state = {}
    for section in (saved or {}).get("sections", []):
        section_id = str(section.get("id", ""))
        if not section_id:
            continue
        state[section_id] = {
            "id": section_id,
            "title": str(section.get("title", "")),
            "body": str(section.get("body", "")),
        }
    return state


def normalize_editor_section_body(text: object, part_id: str) -> str:
    """Normalize generated/editor text before it reaches the HWPX patch layer."""
    if part_id in ENABLED_EDITOR_PART_IDS:
        return sanitize_editor_part_response(str(text or ""), part_id)
    normalized = strip_editor_part_headings(str(text or ""), part_id)
    normalized = markdown_table_to_report_text(normalized)
    if part_id in CRITERIA_REPORT_PART_IDS:
        normalized = sanitize_criteria_report_prose(normalized)
    return normalized.strip()


def ensure_summary_overall_values(text: str, overall: dict) -> str:
    if not overall:
        return text
    summary = str(text or "").strip()
    if summary.startswith("{"):
        return summary
    score_text = f"{overall.get('score')}/{overall.get('maxScore', 20)}점"
    koica_grade = str(overall.get("koicaGrade") or "").strip()
    government_grade = str(overall.get("governmentGrade") or "").strip()
    additions = []
    if score_text and score_text not in summary:
        additions.append(f"종합점수는 {score_text}")
    if koica_grade and koica_grade not in summary:
        additions.append(f"KOICA 평가등급은 {koica_grade}")
    if government_grade and government_grade not in summary:
        additions.append(f"국무조정실 평가등급은 {government_grade}")
    if not additions:
        return summary
    suffix = ", ".join(additions) + "로 정리된다."
    if not summary:
        return suffix
    return summary.rstrip(" .") + " " + suffix


def report_editor_payload() -> dict:
    context = current_report_context()
    saved = read_report_editor_state()
    saved_matches_generator = bool(saved and saved.get("generatorVersion") == REPORT_GENERATOR_VERSION)
    if saved_matches_generator:
        sections = [section for section in saved.get("sections", []) if is_enabled_editor_item(section)]
    else:
        sections = []
    section_to_part = {
        str(part.get("sectionId") or part.get("id")): str(part.get("id"))
        for part in editor_report_parts()
    }
    normalized_sections = []
    for section in sections:
        section_id = str(section.get("id", ""))
        part_id = section_to_part.get(section_id, section_id)
        body = normalize_editor_section_body(str(section.get("body", "")), part_id)
        if part_id == "summary-ko":
            body = ensure_summary_overall_values(body, context.get("overall", {}))
        normalized_sections.append({**section, "body": body})
    sections_by_id = {
        str(section.get("id")): section
        for section in normalized_sections
        if is_enabled_editor_item(section) and str(section.get("id") or "")
    }
    sections = []
    for part in editor_report_parts():
        if not is_enabled_editor_item(part):
            continue
        section_id = str(part.get("sectionId") or part.get("id"))
        existing = sections_by_id.get(section_id)
        sections.append(existing or {
            "id": section_id,
            "title": str(part.get("title", "")),
            "body": "",
        })
    return {
        "project": context["project"],
        "overall": context.get("overall", {}),
        "criteria": context.get("criteria", []),
        "updatedAt": saved.get("updatedAt") if saved_matches_generator else None,
        "source": "saved" if saved_matches_generator else "llm-draft",
        "generatorVersion": REPORT_GENERATOR_VERSION,
        "rhwp": {
            "template": SAMPLE_REPORT_HWP_PATH.name,
            "extraction": "rhwp 파싱 컨텍스트와 평가자료 기반 섹션 초안",
        },
        "sections": sections,
    }


def save_report_editor(body: dict) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    context = current_report_context()
    sections = body.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    previous = read_report_editor_state() or {}
    section_to_part = {
        str(part.get("sectionId") or part.get("id")): str(part.get("id"))
        for part in editor_report_parts()
    }
    normalized = []
    for index, section in enumerate(sections):
        if not is_enabled_editor_item(section):
            continue
        section_id = str(section.get("id", f"section-{index}"))
        part_id = section_to_part.get(section_id, section_id)
        body_text = normalize_editor_section_body(section.get("body", ""), part_id)
        if part_id == "summary-ko":
            body_text = ensure_summary_overall_values(body_text, context.get("overall", {}))
        normalized.append({
            "id": section_id,
            "title": str(section.get("title", "")),
            "body": body_text,
        })
    state = {
        "project": context["project"],
        "generatorVersion": REPORT_GENERATOR_VERSION,
        "sections": normalized,
        "partFingerprints": body.get("partFingerprints") if isinstance(body.get("partFingerprints"), dict) else previous.get("partFingerprints", {}),
        "partSources": body.get("partSources") if isinstance(body.get("partSources"), dict) else previous.get("partSources", {}),
        "updatedAt": now_label(),
    }
    REPORT_EDITOR_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, **state}


def reset_report_editor_to_template() -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    existed = REPORT_EDITOR_STATE_PATH.exists()
    if existed:
        REPORT_EDITOR_STATE_PATH.unlink()
    context = current_report_context()
    return {
        "reset": True,
        "removedSavedReport": existed,
        "source": "template",
        "project": context.get("project", {}),
        "updatedAt": None,
        "sections": [],
        "message": "저장된 AI 작성본을 초기화하고 원본 5-1 양식을 열 준비가 완료되었습니다.",
    }


def revise_report_section(body: dict) -> dict:
    context = current_report_context()
    request_section = body.get("section") if isinstance(body.get("section"), dict) else None
    sections = body.get("sections") if isinstance(body.get("sections"), list) else []
    part_id = str(body.get("partId") or body.get("sectionId") or "")
    editor_part = next((item for item in editor_report_parts() if item["id"] == part_id), None)
    section_id = str((editor_part or {}).get("sectionId") or body.get("sectionId") or part_id)
    if part_id not in ENABLED_EDITOR_PART_IDS and section_id not in ENABLED_EDITOR_SECTION_IDS:
        raise ValueError("현재 생성 가능한 섹션은 1~27번 AI 작성/수정 섹션입니다.")
    current_section = request_section if request_section and str(request_section.get("id")) in {section_id, part_id} else None
    current_section = current_section or next((section for section in sections if str(section.get("id")) == section_id), None)
    if not current_section:
        current_section = next((section for section in sections if str(section.get("id")) == part_id), None)
    if not current_section and sections:
        current_section = sections[0]
    part = editor_part or next((item for item in REPORT_PART_PROMPTS if item["id"] == section_id), None)
    if not part:
        part = next(
            (
                item for item in REPORT_PART_PROMPTS
                if section_id in item["id"] or item["id"] in section_id
            ),
            None,
        )
    user_request = str(body.get("message") or "").strip()
    if not user_request:
        raise ValueError("message is required")
    if part_id == "toc":
        from ..hwpx.patchers import read_toc_page_map

        page_numbers = read_toc_page_map()
        content = structured_slots_to_json("toc", {
            "remove_page_notice": "",
            "page_numbers": page_numbers,
        })
        return {
            "ok": True,
            "partId": part_id,
            "sectionId": section_id,
            "title": (part or current_section or {}).get("title", ""),
            "content": content,
            "message": (
                "Section 2는 LLM 생성 없이 PDF/페이지맵 산출값만 사용합니다."
                if page_numbers
                else "Section 2는 LLM 생성 없이 처리합니다. PDF 기반 toc_page_map.json이 없어서 페이지 번호는 원본 값을 유지합니다."
            ),
        }
    user_priority_instruction = (
        f"사용자 요청 우선으로 반영해주세요: {user_request}\n"
        "단, 사용자 요청이 선택 섹션의 범위를 벗어나거나 확인 가능한 근거와 충돌하면 선택 섹션 안에서 반영 가능한 방식으로 조정하고, "
        "근거가 없는 새 사실은 만들지 마세요."
    )
    fallback_text = str((current_section or {}).get("body") or "")
    if not OPENROUTER.api_key:
        content = sanitize_editor_part_response(
            fallback_text + f"\n\n자동 초안 생성 제약: AI 수정 요청({user_request})을 반영하려면 OPENROUTER_API_KEY 설정이 필요함.",
            part_id,
            user_request,
        )
        return {
            "ok": False,
            "partId": part_id,
            "sectionId": section_id,
            "title": (part or current_section or {}).get("title", ""),
            "content": enforce_editor_part_content(content, part_id, context),
            "message": "OPENROUTER_API_KEY가 없어 로컬 안내문을 반환했습니다.",
        }
    reference_bundle = part_reference_documents(part or {})
    if part_id in REPORT_FULL_REFERENCE_DISABLED_PARTS:
        reference_bundle = {
            **reference_bundle,
            "uploadedDocuments": [],
            "missingEvidence": [],
            "notes": [
                *(reference_bundle.get("notes") or []),
                "이 종합 파트는 원문 문서를 재참조하지 않고 prior_analysis_sections와 기준별 평가결과를 종합한다.",
            ],
        }
    part_specific_inputs = {
        "project": context["project"],
        "overall": context["overall"] if part_id == "grade" else {},
        "criteria": [
            item for item in context["criteria"]
            if item.get("id") in set(reference_bundle.get("criteria") or [])
        ],
        "references": reference_bundle,
    }
    full_reference_corpus = build_full_reference_corpus(part or {})
    if part_id == "grade":
        part_specific_inputs["overall"] = context["overall"]
    if part_id.startswith("criteria-"):
        suffix = part_id.replace("criteria-", "")
        criterion_id_map = {
            "relevance": "relevance",
            "coherence": "coherence",
            "effectiveness": "effectiveness",
            "efficiency": "efficiency",
            "sustainability": "sustainability",
        }
        criterion_id = criterion_id_map.get(suffix)
        selected_criteria = [
            item for item in context["criteria"] if item.get("id") == criterion_id
        ] or context["criteria"]
        part_specific_inputs["criteria"] = [
            {key: value for key, value in item.items() if key != "score"}
            for item in selected_criteria
        ]
    current_part_draft = current_section
    prior_analysis_sections = prior_analysis_sections_for_part(part_id, sections, section_id)
    llm_context = {
        "selected_section_only": True,
        "report_context": {
            "report_type": "KOICA 5-1 종료평가 결과보고서",
            "project": context.get("project", {}),
        },
        "section_to_write": {
            "part_id": part_id,
            "section_id": section_id,
            "title": (part or {}).get("title", ""),
            "writing_prompt": prompt_with_sample_reference_usage((part or {}).get("prompt", "")),
            "required_inputs": (part or {}).get("requiredInputs") or (part or {}).get("required_inputs") or [],
        },
        "reference_plan": {
            "criteria": (part or {}).get("referenceCriteria", []),
            "evidence": (part or {}).get("referenceEvidence", {}),
            "notes": (part or {}).get("referenceNotes", []),
        },
        "sample_reference_for_this_section": sample_reference_for_editor_part(part or {}),
        "previous_text": current_part_draft,
        "revision_policy": (
            "When the user asks to revise a section, treat previous_text as the current edited version of that exact section. "
            "Regenerate only that section by applying user_priority_instruction to previous_text, while keeping evidence-based facts "
            "and section structure unless the request explicitly changes them."
        ),
        "user_request": user_request,
        "user_priority_instruction": user_priority_instruction,
        "content_inputs": part_specific_inputs,
        "prior_analysis_sections": prior_analysis_sections,
        "reference_corpus": full_reference_corpus,
        "detailed_evidence_writing": part_id in DETAILED_EVIDENCE_WRITING_PART_IDS,
        "response_requirements": editor_part_output_contract(part_id),
        "grade_score_rows": criterion_grade_rows(context) if part_id == "grade" else [],
        "rule": (
            "Do not write or revise other report parts. Use only the selected section, prior_analysis_sections, available criteria evaluations, "
            "reference_corpus, and uploaded/supporting documents assigned to this selected section. For summary/conclusion/feedback/lessons parts, prior_analysis_sections and criteria evaluations are primary; use assigned source documents only to substantiate, classify, or fill gaps in the synthesis. If reference_corpus, uploaded documents, prior_analysis_sections, or criteria evaluations "
            "are sufficient for a reasonable judgement, write the section as a completed report section and do not list optional "
            "unfilled evidence slots as missing. When evidence is thin, write a conservative synthesis from the available project/context materials instead of inserting a missing-info marker. For claim support, use "
            "any assigned document, supporting document, or saved criterion evaluation. For detailed_evidence_writing sections, write more than a placeholder fill: cite or name the supporting evidence in prose, synthesize multiple sources when available, and explain the reasoning behind the evaluation judgement. Do not include full-report content unless this selected part specifically requires it."
        ),
    }
    result = OPENROUTER.request_chat_completion(
        OPENROUTER.build_messages(
            (
                "You are an isolated editor for exactly one region of a KOICA 5-1 final evaluation report. "
                + "Start from section_to_write.writing_prompt, section_to_write.required_inputs, reference_plan, reference_corpus, sample_reference_for_this_section, previous_text, and response_requirements. "
                + "Then apply revision_policy and user_priority_instruction as the highest-priority revision instructions for the selected section. "
                + "Use only the selected section described by section_to_write, previous_text, revision_policy, user_request, user_priority_instruction, content_inputs, prior_analysis_sections, reference_corpus, sample_reference_for_this_section, and response_requirements. "
                + "Never generate, summarize, preview, or mention any other report part. "
                + "Follow response_requirements strictly. For enabled sections 1 through 10, return the required JSON object only. No explanations and no Markdown fences. "
                + "For criteria parts, never use scoring memo labels such as 평가점수, 판단, 근거, 한계, 점수 산정 이유; write finished report prose instead. "
                + "For summary, grade, conclusion, working/nonworking factors, feedback, and lessons, synthesize prior_analysis_sections and saved criteria evaluations first; for feedback and lessons, use the limited assigned source corpus to substantiate recommendations, stakeholders, evidence, and checklist questions where needed. "
                + "Before drafting, inspect prior_analysis_sections, reference_corpus documents when present, and saved criteria evaluations. If the provided analysis contains reasonable evidence, synthesize it into final prose. "
                + "For detailed_evidence_writing=true, write a substantive report section grounded in the available materials. Mention source document names, evidenceName values, or saved evaluation sources naturally in the prose when they support a claim. Prefer paraphrase and synthesis; use only short direct quotations. Connect evidence to interpretation, evaluation judgement, limitations, and implications instead of merely filling a slot. "
                + "If direct evidence is limited after checking the corpus, keep the section complete and state the most conservative evidence-based judgement without a missing-info marker. "
                + "Do not copy sample report sentences."
            ),
            llm_context,
        )
    )
    content = result.get("content") or fallback_text
    content = sanitize_editor_part_response(content, part_id, user_request)
    content = enforce_editor_part_content(content, part_id, context)
    return {
        "ok": bool(result.get("ok")),
        "partId": part_id,
        "sectionId": section_id,
        "title": (part or current_section or {}).get("title", ""),
        "content": content,
        "raw": result,
    }


def generate_report_editor_auto_draft(body: dict) -> dict:
    context = current_report_context()
    saved_state = read_report_editor_state() or {}
    reset = bool(body.get("reset"))
    force = bool(body.get("force") or reset)
    if reset:
        base_sections = []
        saved_state = {}
    elif isinstance(body.get("sections"), list) and body.get("sections"):
        base_sections = body.get("sections")
    elif saved_state.get("sections"):
        base_sections = saved_state.get("sections", [])
    else:
        base_sections = []
    parts = [
        part for part in editor_report_parts()
        if str(part.get("id")) in ENABLED_EDITOR_PART_IDS or str(part.get("sectionId")) in ENABLED_EDITOR_SECTION_IDS
    ]
    requested_part_ids = {str(value) for value in body.get("partIds", []) if str(value)}
    if requested_part_ids:
        parts = [part for part in parts if str(part.get("id")) in requested_part_ids]
        force = True
    if not parts:
        raise ValueError("Cover section prompt was not found")
    workers = max(1, min(int(os.getenv("REPORT_DRAFT_WORKERS", "6")), len(parts)))
    overall_timeout = int(os.getenv("REPORT_DRAFT_TIMEOUT_SECONDS", "75"))
    previous_fingerprints = saved_state.get("partFingerprints", {}) if isinstance(saved_state.get("partFingerprints"), dict) else {}
    previous_sources = saved_state.get("partSources", {}) if isinstance(saved_state.get("partSources"), dict) else {}
    current_fingerprints = {str(part.get("id")): part_fingerprint(part) for part in parts}
    current_sources = {str(part.get("id")): part_related_sources(part) for part in parts}
    section_map = report_editor_state_sections_map({"sections": base_sections})
    stale_parts = []
    skipped_results = []
    for part in parts:
        part_id = str(part.get("id"))
        section_id = str(part.get("sectionId") or part_id)
        current_section = section_map.get(section_id)
        is_stale = (
            force
            or previous_fingerprints.get(part_id) != current_fingerprints.get(part_id)
            or not current_section
            or not str(current_section.get("body", "")).strip()
        )
        if is_stale:
            stale_parts.append(part)
        else:
            skipped_results.append({
                "ok": True,
                "skipped": True,
                "partId": part_id,
                "sectionId": section_id,
                "title": current_section.get("title") or part.get("title", ""),
                "content": strip_editor_part_headings(current_section.get("body", ""), part_id),
                "fingerprint": current_fingerprints.get(part_id),
                "reason": "관련 문서 변경 없음: 기존 생성 결과 재사용",
            })
    request_message = (
        "이 섹션의 작성 프롬프트, response_requirements, 저장된 기준별 평가결과, reference_plan의 직접 근거와 supporting 문서를 사용해서 제출 가능한 초안을 작성해줘. "
        "점수와 등급은 평가등급 결과표에서만 직접 표기하고, 기준별 본문(criteria-*)에는 '평가점수: n점/4점'이나 점수 산정 메모를 쓰지 마. "
        "previous_text는 참고용 원자료일 뿐이므로 판단/근거/한계 라벨 형식은 버리고, 샘플 보고서처럼 소제목과 줄글 문단으로 다시 작성해. "
        "content_inputs.criteria 및 grade_score_rows 값은 판단 수준을 정합화하는 참고값으로만 사용하고, 값이 있는데 1점으로 초기화하지 마. "
        "등록 문서와 기준별 평가결과로 판단 가능한 내용은 완성 문장으로 작성하고, optional 슬롯이 비어 있다는 이유만으로 보완 필요를 남기지 마. "
        "상세 서술형 섹션은 reference_corpus와 저장된 평가결과를 확인해 문서명 또는 evidenceName을 본문에 자연스럽게 인용하고, 근거-해석-평가판단-한계/시사점 흐름으로 충분히 설명해줘. "
        "정말 근거가 없는 주장에만 자료 기반 보수적 서술을 명시해줘. 다른 파트 내용이나 관련 없는 업로드 문서는 사용하지 마."
    )

    def section_for_part(part: dict) -> dict:
        section_id = str(part.get("sectionId") or part.get("id"))
        found = next(
            (
                section for section in section_map.values()
                if str(section.get("id")) in {section_id, str(part.get("id"))}
            ),
            None,
        )
        return found or {"id": section_id, "title": part.get("title", ""), "body": ""}

    def run_part(part: dict) -> dict:
        section_id = str(part.get("sectionId") or part.get("id"))
        part_id = str(part.get("id"))
        started = now_label()
        print(f"[auto-draft] start {part_id} -> {section_id}", flush=True)
        try:
            result = revise_report_section({
                "message": request_message,
                "partId": part_id,
                "sectionId": section_id,
                "section": section_for_part(part),
                "sections": list(section_map.values()),
            })
            result["startedAt"] = started
            result["finishedAt"] = now_label()
            result["timedOut"] = False
            print(f"[auto-draft] done {part_id}", flush=True)
            return result
        except Exception as exc:  # noqa: BLE001
            print(f"[auto-draft] fail {part_id}: {exc}", flush=True)
            return {
                "ok": False,
                "partId": part_id,
                "sectionId": section_id,
                "title": part.get("title", ""),
                "content": f"자동 초안 생성 제약: {part.get('title') or section_id} 자동 초안 생성 실패({exc}).",
                "startedAt": started,
                "finishedAt": now_label(),
                "timedOut": False,
            }

    def merge_results_into_section_map(batch_results: list[dict]) -> None:
        for result in batch_results:
            section_id = str(result.get("sectionId") or result.get("partId"))
            part_id = str(result.get("partId") or section_id)
            section_map[section_id] = {
                "id": section_id,
                "title": str(result.get("title") or section_id),
                "body": strip_editor_part_headings(str(result.get("content") or ""), part_id),
            }

    def run_part_batch(batch_parts: list[dict]) -> list[dict]:
        if not batch_parts:
            return []
        batch_results: list[dict] = []
        executor = ThreadPoolExecutor(max_workers=min(workers, len(batch_parts)))
        futures = {executor.submit(run_part, part): part for part in batch_parts}
        pending = set(futures)
        deadline = datetime.now().timestamp() + overall_timeout
        while pending:
            remaining = deadline - datetime.now().timestamp()
            if remaining <= 0:
                break
            done, pending = wait(pending, timeout=min(2, remaining), return_when=FIRST_COMPLETED)
            for future in done:
                part = futures[future]
                try:
                    result = future.result()
                    result["fingerprint"] = current_fingerprints.get(str(part.get("id")))
                    batch_results.append(result)
                except Exception as exc:  # noqa: BLE001
                    part_id = str(part.get("id"))
                    section_id = str(part.get("sectionId") or part_id)
                    batch_results.append({
                        "ok": False,
                        "partId": part_id,
                        "sectionId": section_id,
                        "title": part.get("title", ""),
                        "content": f"자동 초안 생성 제약: {part.get('title') or section_id} 자동 초안 생성 실패({exc}).",
                        "timedOut": False,
                        "fingerprint": current_fingerprints.get(part_id),
                    })
        for future in pending:
            part = futures[future]
            part_id = str(part.get("id"))
            section_id = str(part.get("sectionId") or part_id)
            future.cancel()
            print(f"[auto-draft] timeout {part_id}", flush=True)
            batch_results.append({
                "ok": False,
                "partId": part_id,
                "sectionId": section_id,
                "title": part.get("title", ""),
                "content": (
                    f"자동 초안 생성 제약: {part.get('title') or section_id} 자동 초안 생성 시간이 초과되어 "
                    "이 파트는 건너뛰었습니다. 업로드 자료를 확인한 뒤 AI 수정 요청에서 다시 생성해 주세요."
                ),
                "timedOut": True,
                "finishedAt": now_label(),
                "fingerprint": current_fingerprints.get(part_id),
            })
        executor.shutdown(wait=False, cancel_futures=True)
        return batch_results

    results: list[dict] = list(skipped_results)
    if stale_parts:
        source_backed_parts = [part for part in stale_parts if str(part.get("id")) not in REPORT_FULL_REFERENCE_DISABLED_PARTS]
        synthesis_parts = [part for part in stale_parts if str(part.get("id")) in REPORT_FULL_REFERENCE_DISABLED_PARTS]
        first_results = run_part_batch(source_backed_parts)
        results.extend(first_results)
        merge_results_into_section_map(first_results)
        second_results = run_part_batch(synthesis_parts)
        results.extend(second_results)
        merge_results_into_section_map(second_results)
    else:
        print("[auto-draft] all parts skipped; cached drafts are fresh", flush=True)

    order = {str(part.get("id")): index for index, part in enumerate(parts)}
    results.sort(key=lambda item: order.get(str(item.get("partId")), 999))
    by_section = {
        str(section.get("id")): {
            "id": str(section.get("id")),
            "title": str(section.get("title", "")),
            "body": str(section.get("body", "")),
        }
        for section in base_sections
        if section.get("id")
    }
    for result in results:
        section_id = str(result.get("sectionId") or result.get("partId"))
        part_id = str(result.get("partId") or section_id)
        by_section[section_id] = {
            "id": section_id,
            "title": str(result.get("title") or section_id),
            "body": strip_editor_part_headings(str(result.get("content") or ""), part_id),
        }

    output_parts = editor_report_parts() if requested_part_ids else parts
    ordered_section_ids = [
        str(part.get("sectionId") or part.get("id"))
        for part in output_parts
    ]
    sections = [by_section[section_id] for section_id in ordered_section_ids if section_id in by_section]
    if any(not is_enabled_editor_item(section) for section in sections):
        sections = polish_report_sections_for_final(context, sections)
    merged_fingerprints = dict(previous_fingerprints)
    merged_sources = dict(previous_sources)
    for result in results:
        part_id = str(result.get("partId", ""))
        if not part_id:
            continue
        merged_fingerprints[part_id] = current_fingerprints.get(part_id)
        merged_sources[part_id] = current_sources.get(part_id)
    saved = save_report_editor({
        "sections": sections,
        "partFingerprints": merged_fingerprints,
        "partSources": merged_sources,
    })
    return {
        "ok": True,
        "workers": workers,
        "timeoutSeconds": overall_timeout,
        "generated": len(stale_parts),
        "skipped": len(skipped_results),
        "done": len([item for item in results if item.get("ok")]),
        "failed": len([item for item in results if not item.get("ok")]),
        "total": len(parts),
        "results": results,
        "sections": saved.get("sections", sections),
        "updatedAt": saved.get("updatedAt"),
        "project": context.get("project", {}),
    }


def normalize_exported_hwp(body: dict) -> dict:
    file_name = safe_filename_part(body.get("fileName", "report"), "report") + ".hwp"
    encoded = str(body.get("data") or "")
    if not encoded:
        raise ValueError("data is required")
    try:
        raw = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError("invalid base64 data") from exc
    if len(raw) < 16:
        raise ValueError("HWP data is too small")
    with tempfile.TemporaryDirectory(prefix="rhwp_save_") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "source.hwp"
        source.write_bytes(raw)
        info_before = subprocess.run(
            [RHWP_BIN, "info", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RHWP_TIMEOUT_SECONDS,
        )
        if info_before.returncode != 0:
            raise ValueError(f"rhwp info failed: {short_text(info_before.stderr or info_before.stdout, 500)}")

        info_text = info_before.stdout or ""
        page_match = re.search(r"페이지\s*수:\s*(\d+)", info_text)
        section_match = re.search(r"구역\s*수:\s*(\d+)", info_text)
        page_count = int(page_match.group(1)) if page_match else 0
        section_count = int(section_match.group(1)) if section_match else 0
        if page_count < 8 or section_count < 4:
            raise ValueError(
                f"HWP export looks truncated: sections={section_count}, pages={page_count}. "
                "에디터에 보이는 전체 문서가 저장 파일에 반영되지 않았습니다."
            )

        text_dir = tmp_path / "text"
        text_export = subprocess.run(
            [RHWP_BIN, "export-text", str(source), "-o", str(text_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RHWP_TIMEOUT_SECONDS,
        )
        if text_export.returncode != 0:
            raise ValueError(f"rhwp text validation failed: {short_text(text_export.stderr or text_export.stdout, 500)}")
        exported_files = sorted(text_dir.glob("*.txt"))
        exported_text = "\n".join(file.read_text(encoding="utf-8", errors="replace") for file in exported_files)
        if len(exported_text.strip()) < 1500 or "평가" not in exported_text or "첨부" not in exported_text:
            raise ValueError(
                "HWP export text validation failed: 저장 파일 본문이 표지/목차 수준으로만 추출됩니다."
            )

        normalized = source.read_bytes()
    return {
        "ok": True,
        "fileName": file_name,
        "bytes": len(normalized),
        "pages": page_count,
        "sections": section_count,
        "data": base64.b64encode(normalized).decode("ascii"),
    }


def validate_exported_hwpx(body: dict) -> dict:
    file_stem = safe_filename_part(body.get("fileName", "report"), "report")
    file_stem = re.sub(r"\.hwpx$", "", file_stem, flags=re.IGNORECASE)
    file_name = file_stem + ".hwpx"
    encoded = str(body.get("data") or "")
    if not encoded:
        raise ValueError("data is required")
    try:
        raw = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError("invalid base64 data") from exc
    if len(raw) < 128:
        raise ValueError("HWPX data is too small")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = set(archive.namelist())
            required_any = [
                "mimetype",
                "Contents/content.hpf",
                "META-INF/container.xml",
            ]
            if not any(name in names for name in required_any):
                raise ValueError("HWPX package header files were not found")
            if not any(name.startswith("Contents/section") and name.endswith(".xml") for name in names):
                raise ValueError("HWPX body section files were not found")
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"HWPX zip validation failed at {bad_member}")
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid HWPX zip package") from exc
    with tempfile.TemporaryDirectory(prefix="rhwp_hwpx_") as tmp:
        hwpx_path = Path(tmp) / "source.hwpx"
        hwpx_path.write_bytes(raw)
        try:
            info = subprocess.run(
                [RHWP_BIN, "info", str(hwpx_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=RHWP_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                section_count = sum(
                    1
                    for name in archive.namelist()
                    if name.startswith("Contents/section") and name.endswith(".xml")
                )
            return {
                "ok": True,
                "fileName": file_name,
                "bytes": len(raw),
                "pages": 0,
                "sections": section_count,
                "validation": "zip-only; rhwp executable not found",
                "data": base64.b64encode(raw).decode("ascii"),
            }
        if info.returncode != 0:
            raise ValueError(f"rhwp HWPX validation failed: {short_text(info.stderr or info.stdout, 500)}")
        info_text = info.stdout or ""
        page_match = re.search(r"페이지 수:\s*(\d+)", info_text)
        section_match = re.search(r"구역 수:\s*(\d+)", info_text)
        paper_match = re.search(r"구역0 용지:\s*(\d+)\s*[×x]\s*(\d+)\s*HWPUNIT", info_text)
        page_count = int(page_match.group(1)) if page_match else 0
        section_count = int(section_match.group(1)) if section_match else 0
        paper_width = int(paper_match.group(1)) if paper_match else 0
        paper_height = int(paper_match.group(2)) if paper_match else 0
        if section_count < 5 or page_count < 8:
            raise ValueError(
                f"HWPX validation failed: 본문 구역/페이지가 부족합니다. sections={section_count}, pages={page_count}"
            )
        if paper_width < 10000 or paper_height < 10000:
            raise ValueError(
                f"HWPX validation failed: 용지 크기가 비정상입니다. paper={paper_width}x{paper_height}"
            )
        text_dir = Path(tmp) / "text"
        text_dir.mkdir(parents=True, exist_ok=True)
        text_export = subprocess.run(
            [RHWP_BIN, "export-text", str(hwpx_path), "-o", str(text_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RHWP_TIMEOUT_SECONDS,
        )
        if text_export.returncode != 0:
            raise ValueError(f"rhwp HWPX text validation failed: {short_text(text_export.stderr or text_export.stdout, 500)}")
        exported_text = "\n".join(
            file.read_text(encoding="utf-8", errors="replace")
            for file in sorted(text_dir.glob("*.txt"))
        )
        if len(exported_text.strip()) < 1500 or "평가" not in exported_text:
            raise ValueError("HWPX validation failed: 저장 파일 본문이 표지 수준으로만 추출됩니다.")
    return {
        "ok": True,
        "fileName": file_name,
        "bytes": len(raw),
        "pages": page_count,
        "sections": section_count,
        "data": base64.b64encode(raw).decode("ascii"),
    }

