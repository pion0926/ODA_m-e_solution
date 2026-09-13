from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from report_prompts import EDITOR_REPORT_PARTS
from ..documents.evidence_store import list_uploaded_documents


ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = ROOT / "data" / "report_section_settings.json"


def load_section_overrides() -> dict:
    if not SETTINGS_PATH.exists():
        return {"version": 1, "sections": {}}
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"version": 1, "sections": {}}
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sections": {}}


def editor_report_parts() -> list[dict]:
    overrides = load_section_overrides().get("sections", {})
    parts = []
    for source in EDITOR_REPORT_PARTS:
        part = deepcopy(source)
        override = overrides.get(str(part.get("id")), {}) if isinstance(overrides, dict) else {}
        for key in ("description", "prompt", "additionalInstructions", "customReferenceDocumentIds"):
            if key in override:
                part[key] = deepcopy(override[key])
        part["basePrompt"] = source.get("prompt", "")
        part["description"] = part.get("description") or f"{part.get('title', '')} 섹션의 작성 목적과 산출 형식을 관리합니다."
        if part.get("additionalInstructions"):
            part["prompt"] = str(part.get("prompt", "")).rstrip() + "\n\n[담당자 추가 지침]\n" + str(part["additionalInstructions"]).strip()
        parts.append(part)
    return parts


def reference_document_options() -> list[dict]:
    documents = []
    seen = set()
    for criterion_id in ("relevance", "coherence", "effectiveness", "efficiency", "sustainability", "impact"):
        for document in list_uploaded_documents(criterion_id):
            document_id = str(document.get("id") or "")
            if not document_id or document_id in seen:
                continue
            seen.add(document_id)
            documents.append({"id": document_id, "criterionId": criterion_id, "fileName": document.get("fileName", ""), "evidenceName": document.get("evidenceName", ""), "uploadedAt": document.get("uploadedAt", "")})
    return sorted(documents, key=lambda item: (item["criterionId"], item["evidenceName"], item["fileName"]))


def section_settings_payload() -> dict:
    state = load_section_overrides()
    overrides = state.get("sections", {}) if isinstance(state.get("sections"), dict) else {}
    editable = []
    for part in editor_report_parts():
        override = overrides.get(str(part.get("id")), {})
        editable.append({**part, "prompt": override.get("prompt", part.get("basePrompt", part.get("prompt", ""))), "additionalInstructions": override.get("additionalInstructions", "")})
    return {"version": state.get("version", 1), "editorParts": editable, "referenceDocuments": reference_document_options()}


def save_section_settings(body: dict) -> dict:
    incoming = body.get("sections", []) if isinstance(body, dict) else []
    valid_ids = {str(part.get("id")) for part in EDITOR_REPORT_PARTS}
    overrides = {}
    for item in incoming:
        if not isinstance(item, dict) or str(item.get("id")) not in valid_ids:
            continue
        part_id = str(item["id"])
        overrides[part_id] = {
            "description": str(item.get("description", "")).strip(),
            "prompt": str(item.get("prompt", "")).strip(),
            "additionalInstructions": str(item.get("additionalInstructions", "")).strip(),
            "customReferenceDocumentIds": list(dict.fromkeys(str(value) for value in item.get("customReferenceDocumentIds", []) if str(value))),
        }
    current = load_section_overrides()
    saved = {"version": int(current.get("version", 1)) + 1, "sections": overrides}
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return section_settings_payload()
