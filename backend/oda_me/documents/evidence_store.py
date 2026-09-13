from __future__ import annotations

from ..core import *
from ..clients.openrouter import OPENROUTER
from .intake_rules import rules_with_slots, validate_and_save_rules

def document_meta_dir(criterion_id: str) -> Path:
    return UPLOAD_DIR / criterion_id / "_meta"


def persist_document_metadata(criterion_id: str, document: dict) -> None:
    meta_dir = document_meta_dir(criterion_id)
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{document['id']}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def list_uploaded_documents(criterion_id: str) -> list[dict]:
    meta_dir = document_meta_dir(criterion_id)
    if not meta_dir.exists():
        return []
    documents = []
    for path in sorted(meta_dir.glob("*.json")):
        try:
            documents.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return documents


def find_uploaded_document(criterion_id: str, document_id: str) -> tuple[dict | None, Path | None]:
    meta_path = document_meta_dir(criterion_id) / f"{document_id}.json"
    if not meta_path.exists():
        return None, None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")), meta_path
    except json.JSONDecodeError:
        return None, meta_path


def delete_uploaded_document(criterion_id: str, document_id: str) -> dict | None:
    document, meta_path = find_uploaded_document(criterion_id, document_id)
    if not document:
        return None
    for key in ("rawPath", "textPath"):
        path_value = document.get(key)
        if not path_value:
            continue
        path = Path(path_value)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    if meta_path:
        meta_path.unlink(missing_ok=True)
    return document


def remove_document_metadata_by_evidence(criterion_id: str, evidence_name: str) -> None:
    meta_dir = document_meta_dir(criterion_id)
    if not meta_dir.exists():
        return
    for path in meta_dir.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if document.get("evidenceName") == evidence_name:
            path.unlink(missing_ok=True)


def attach_uploaded_documents() -> None:
    for criterion in CRITERIA:
        documents = list_uploaded_documents(criterion["id"])
        criterion["uploadedDocuments"] = documents
        criterion["evidenceStatus"] = {document.get("evidenceName", ""): document for document in documents}


def evaluation_path(criterion_id: str) -> Path:
    return EVALUATION_DIR / f"{criterion_id}.json"


def clean_evaluation_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned_lines = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = line.strip()
        if re.fullmatch(r"[-–—]{3,}", cleaned):
            continue
        cleaned = cleaned.replace("**", "")
        cleaned = re.sub(r"^[-•ㅇ]\s*평가결과\s*[:：]\s*", "- ", cleaned)
        cleaned = re.sub(r"^평가결과\s*[:：]\s*", "", cleaned)
        replacements = {
            "하였습니다": "하였음",
            "되었습니다": "되었음",
            "어렵습니다": "어려움",
            "필수적입니다": "필수",
            "부족합니다": "부족",
            "부재합니다": "부재",
            "불가능합니다": "불가능",
            "필요합니다": "필요",
            "있습니다": "있음",
            "없습니다": "없음",
            "합니다": "함",
            "됩니다": "됨",
            "입니다": "임",
        }
        for before, after in replacements.items():
            cleaned = cleaned.replace(before, after)
        cleaned = re.sub(r"([가-힣\]])[.。]\s*", r"\1 ", cleaned)
        cleaned = re.sub(r"\s+[.。]\s*$", "", cleaned)
        cleaned_lines.append(cleaned.rstrip())
    return "\n".join(cleaned_lines).strip()


def extract_score_from_text(text: str | None) -> int | None:
    if not text:
        return None
    patterns = [
        r"예상\s*점수\s*[:：]?\s*([1-4])\s*점",
        r"평가\s*결과\s*점수\s*[:：]?\s*([1-4])\s*점",
        r"예상점수\s*[:：]?\s*([1-4])\s*점",
        r"종합판정[\s\S]{0,120}?([1-4])\s*점",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text), re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def clean_evaluation_result(evaluation: dict | None) -> dict | None:
    if not evaluation:
        return evaluation
    result = dict(evaluation)
    if result.get("summary"):
        result["summary"] = clean_evaluation_text(result["summary"])
    has_question_scores = False
    sections = []
    for section in result.get("sections", []) or []:
        section_copy = dict(section)
        if section_copy.get("title"):
            section_copy["title"] = clean_evaluation_text(section_copy["title"])
        if section_copy.get("body"):
            section_copy["body"] = clean_evaluation_text(section_copy["body"])
        sections.append(section_copy)
    result["sections"] = sections
    if isinstance(result.get("improvementNeeds"), list):
        result["improvementNeeds"] = [
            clean_evaluation_text(item)
            for item in result.get("improvementNeeds", [])
            if str(item).strip()
        ]
    if isinstance(result.get("questionAssessments"), list):
        cleaned_assessments = []
        for item in result.get("questionAssessments", []):
            if not isinstance(item, dict):
                continue
            cleaned_item = dict(item)
            try:
                cleaned_item["score"] = max(1, min(4, int(round(float(cleaned_item.get("score") or 1)))))
            except (TypeError, ValueError):
                cleaned_item["score"] = 1
            for key in ("question", "finding"):
                if cleaned_item.get(key):
                    cleaned_item[key] = clean_evaluation_text(cleaned_item[key])
            for key in ("evidenceUsed", "evidenceGaps", "actionItems"):
                if isinstance(cleaned_item.get(key), list):
                    cleaned_item[key] = [clean_evaluation_text(value) for value in cleaned_item[key] if str(value).strip()]
            cleaned_assessments.append(cleaned_item)
        result["questionAssessments"] = cleaned_assessments
        has_question_scores = bool(cleaned_assessments)
    if has_question_scores:
        result["score"] = round(
            sum(item["score"] for item in result["questionAssessments"]) / len(result["questionAssessments"]),
            1,
        )
        result["scoreFormula"] = "questionAssessments 평균(소수 첫째 자리 반올림)"
    else:
        text_score = extract_score_from_text(result.get("summary"))
        llm_content = result.get("llm", {}).get("content") if isinstance(result.get("llm"), dict) else None
        text_score = text_score or extract_score_from_text(llm_content)
        if text_score:
            result["score"] = float(text_score)
    return result


def save_evaluation_result(criterion_id: str, evaluation: dict | None) -> None:
    if not evaluation:
        return
    evaluation = clean_evaluation_result(evaluation)
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "criterionId": criterion_id,
        "evaluation": evaluation,
        "score": evaluation.get("score"),
        "savedAt": now_label(),
    }
    evaluation_path(criterion_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_evaluation_result(criterion_id: str) -> dict | None:
    path = evaluation_path(criterion_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return clean_evaluation_result(payload.get("evaluation"))


def apply_persisted_evaluations() -> None:
    for criterion in CRITERIA:
        evaluation = load_evaluation_result(criterion["id"])
        if not evaluation:
            continue
        if criterion_evaluation_needs_refresh(criterion["id"], evaluation):
            refreshed = regenerate_criterion_evaluation(criterion["id"])
            if refreshed:
                evaluation = refreshed
        criterion["evaluationResult"] = evaluation
        if evaluation.get("score"):
            criterion["currentScore4"] = evaluation["score"]
            criterion["scoreStatus"] = "평가 완료"


def criterion_evaluation_needs_refresh(criterion_id: str, evaluation: dict | None) -> bool:
    if not evaluation:
        return False
    if evaluation.get("generatorVersion") == CRITERION_EVALUATION_VERSION:
        return False
    criterion = find_criterion(criterion_id) or {}
    if criterion.get("uploadedDocuments"):
        return True
    sections = evaluation.get("sections") or []
    stale_text = "\n".join(
        [str(evaluation.get("summary", ""))]
        + [str(section.get("title", "")) + "\n" + str(section.get("body", "")) for section in sections if isinstance(section, dict)]
    )
    if re.search(r"업로드되면|업로드되어야|�|\?[가-힣]|[가-힣]\?", stale_text):
        return True
    return False


def regenerate_criterion_evaluation(criterion_id: str) -> dict | None:
    criterion = find_criterion(criterion_id)
    if not criterion:
        return None
    evaluation = generate_criterion_evaluation(criterion_id, None)
    if not evaluation:
        return None
    criterion["evaluationResult"] = evaluation
    if evaluation.get("score"):
        criterion["currentScore4"] = evaluation["score"]
        criterion["scoreStatus"] = "평가 완료"
    save_evaluation_result(criterion_id, evaluation)
    return evaluation


def save_uploaded_document(criterion_id: str, body: dict) -> dict:
    filename = safe_filename(body.get("fileName", "uploaded_file"))
    mime_type = body.get("mimeType", "application/octet-stream")
    raw = base64.b64decode(body.get("contentBase64", ""))
    document_id = uuid.uuid4().hex[:12]
    criterion_upload_dir = UPLOAD_DIR / criterion_id
    criterion_text_dir = TEXT_DIR / criterion_id
    criterion_upload_dir.mkdir(parents=True, exist_ok=True)
    criterion_text_dir.mkdir(parents=True, exist_ok=True)
    raw_path = criterion_upload_dir / f"{document_id}_{filename}"
    raw_path.write_bytes(raw)
    extracted_text, extraction_method = extract_text(raw, filename, mime_type)
    text_path = criterion_text_dir / f"{document_id}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")
    document = {
        "id": document_id,
        "criterionId": criterion_id,
        "evidenceName": body.get("evidenceName", ""),
        "fileName": filename,
        "mimeType": mime_type,
        "size": len(raw),
        "rawPath": str(raw_path),
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
        "analysisMetadata": body.get("analysisMetadata", {}),
        "allocationTrace": body.get("allocationTrace", {}),
        "uploadedAt": now_label(),
    }
    persist_document_metadata(criterion_id, document)
    return document


SHARED_EVIDENCE_RULES = [
    {
        "patterns": ["PDM", "Project Design Matrix", "성과지표"],
        "targets": [
            ("relevance", "집행계획서 및 최신 PDM (Project Design Matrix)"),
            ("effectiveness", "최신 PDM 및 성과지표 실적표"),
        ],
    },
    {
        "patterns": ["ToC", "변화이론", "문제나무", "논리모형"],
        "targets": [("relevance", "변화이론(ToC) 도식도 및 문제나무 분석 자료")],
    },
    {
        "patterns": ["인터뷰", "면담", "사례", "수혜자", "만족도"],
        "targets": [
            ("relevance", "수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)"),
            ("effectiveness", "수혜자 만족도 조사 및 현장점검 기록"),
            ("effectiveness", "수혜자 인터뷰 또는 사례 기록"),
            ("sustainability", "지역사회 참여 및 수용성 확인 자료"),
        ],
    },
    {
        "patterns": ["Baseline", "Endline", "기준선", "종료선", "기초조사"],
        "targets": [
            ("relevance", "예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)"),
            ("effectiveness", "기준선/종료선 조사자료 (Baseline/Endline)"),
        ],
    },
    {
        "patterns": ["MoU", "ROD", "협의의사록", "역할분담", "RACI"],
        "targets": [
            ("relevance", "부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)"),
            ("coherence", "이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서"),
            ("sustainability", "운영 담당 조직의 역할분담 문서"),
        ],
    },
    {
        "patterns": ["JSC", "운영위원회", "회의록", "조정 회의", "공동 의사결정"],
        "targets": [
            ("relevance", "사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록"),
            ("coherence", "운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록"),
            ("efficiency", "주요 활동 간 연계·조정 회의록"),
        ],
    },
    {
        "patterns": ["Change Log", "변경요청", "변경 관리", "시정조치", "지연"],
        "targets": [
            ("relevance", "사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록"),
            ("efficiency", "지연 사유 및 시정조치 기록"),
        ],
    },
    {
        "patterns": ["연차점검", "모니터링", "현장점검"],
        "targets": [
            ("relevance", "정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)"),
            ("effectiveness", "수혜자 만족도 조사 및 현장점검 기록"),
        ],
    },
]


def evidence_exists(criterion_id: str, evidence_name: str, file_name: str | None = None, source_document_id: str | None = None) -> bool:
    for document in list_uploaded_documents(criterion_id):
        if document.get("evidenceName") != evidence_name:
            continue
        if source_document_id and document.get("sourceDocumentId") == source_document_id:
            return True
        if file_name and document.get("fileName") == file_name:
            return True
    return False


def infer_shared_evidence_targets(document: dict) -> list[tuple[str, str]]:
    text = " ".join(
        str(document.get(key, ""))
        for key in ("evidenceName", "fileName", "textPreview")
    )
    targets: list[tuple[str, str]] = []
    for rule in SHARED_EVIDENCE_RULES:
        if any(pattern.lower() in text.lower() for pattern in rule["patterns"]):
            targets.extend(rule["targets"])
    unique = []
    for criterion_id, evidence_name in targets:
        if (criterion_id, evidence_name) not in unique:
            unique.append((criterion_id, evidence_name))
    return unique


def create_shared_document(source_document: dict, criterion_id: str, evidence_name: str) -> dict | None:
    if criterion_id == source_document.get("criterionId") and evidence_name == source_document.get("evidenceName"):
        return None
    if evidence_exists(criterion_id, evidence_name, source_document.get("fileName"), source_document.get("id")):
        return None
    target_upload_dir = UPLOAD_DIR / criterion_id
    target_text_dir = TEXT_DIR / criterion_id
    target_upload_dir.mkdir(parents=True, exist_ok=True)
    target_text_dir.mkdir(parents=True, exist_ok=True)
    document_id = uuid.uuid4().hex[:12]
    source_raw = Path(source_document.get("rawPath", ""))
    source_text = Path(source_document.get("textPath", ""))
    filename = safe_filename(source_document.get("fileName", "shared_document"))
    raw_path = target_upload_dir / f"{document_id}_{filename}"
    text_path = target_text_dir / f"{document_id}.txt"
    try:
        if source_raw.exists():
            shutil.copy2(source_raw, raw_path)
        if source_text.exists():
            shutil.copy2(source_text, text_path)
    except OSError:
        return None
    document = {
        **source_document,
        "id": document_id,
        "criterionId": criterion_id,
        "evidenceName": evidence_name,
        "rawPath": str(raw_path),
        "textPath": str(text_path),
        "uploadedAt": now_label(),
        "matchStatus": "shared_assigned",
        "sharedFrom": {
            "criterionId": source_document.get("criterionId"),
            "evidenceName": source_document.get("evidenceName"),
            "documentId": source_document.get("id"),
        },
        "sourceDocumentId": source_document.get("sourceDocumentId") or source_document.get("id"),
    }
    persist_document_metadata(criterion_id, document)
    return document


def apply_shared_evidence(document: dict) -> list[dict]:
    shared = []
    for criterion_id, evidence_name in infer_shared_evidence_targets(document):
        created = create_shared_document(document, criterion_id, evidence_name)
        if created:
            shared.append(created)
    return shared


def regenerate_affected_criteria(criterion_ids: set[str]) -> dict:
    evaluations = {}
    for criterion_id in sorted(criterion_ids):
        evaluation = regenerate_criterion_evaluation(criterion_id)
        if evaluation:
            evaluations[criterion_id] = evaluation
    return evaluations


def evidence_candidates() -> list[dict]:
    candidates = []
    for criterion in CRITERIA:
        if criterion.get("id") == "impact":
            continue
        for item in criterion.get("evidence", []):
            candidates.append(
                {
                    "criterionId": criterion["id"],
                    "criterionName": criterion["name"],
                    "evidenceName": item.get("name", ""),
                    "category": item.get("category", ""),
                }
            )
    return candidates


def token_set(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", " ", value).lower()
    return {token for token in normalized.split() if len(token) >= 2}


def intake_rules_payload() -> dict:
    return rules_with_slots(evidence_candidates())


def save_intake_rules(payload: dict) -> dict:
    return validate_and_save_rules(payload, evidence_candidates())


def extract_document_metadata(filename: str, extracted_text: str, mime_type: str) -> dict:
    config = intake_rules_payload()
    fields = config.get("metadataFields", [])
    metadata = {
        "title": filename.rsplit(".", 1)[0],
        "documentType": "스프레드시트" if filename.lower().endswith((".xlsx", ".xls", ".csv")) else "문서자료",
        "summary": re.sub(r"\s+", " ", extracted_text).strip()[:700],
        "language": "한국어" if re.search(r"[가-힣]", extracted_text[:3000]) else "영어/기타",
        "qualityFlags": [] if extracted_text.strip() else ["본문 텍스트를 추출하지 못함"],
    }
    task = """ODA 성과관리 자료를 분석해 metadataFields의 key만 사용한 JSON을 반환하세요.
확인되지 않는 값은 빈 문자열 또는 빈 배열로 두고 추측하지 마세요. summary는 사실 중심 3~5문장,
qualityFlags는 결측·중복·불일치·산식·출처 문제를 배열로 작성하세요.
형식: {"metadata": {...}, "qualityScore": 0~100, "analysisNotes": ["..."]}"""
    context = {"fileName": filename, "mimeType": mime_type, "textPreview": extracted_text[:10000], "metadataFields": fields}
    result = OPENROUTER.request_chat_completion(OPENROUTER.build_messages(task, context))
    parsed = parse_llm_json(result.get("content", "")) if result.get("ok") else None
    if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict):
        allowed = {item.get("key") for item in fields}
        metadata.update({key: value for key, value in parsed["metadata"].items() if key in allowed})
        metadata.update({"qualityScore": parsed.get("qualityScore"), "analysisNotes": parsed.get("analysisNotes", []), "analysisMethod": "llm+local"})
    else:
        metadata.update({"analysisMethod": "local", "analysisNotes": ["AI 연결 없이 기본 메타데이터만 추출함"]})
    return metadata


def _legacy_rule_match_candidates(filename: str, extracted_text: str) -> list[dict]:
    source = f"{filename} {extracted_text[:12000]}".lower()
    scored = []
    for rule in intake_rules_payload().get("slotRules", []):
        if not rule.get("enabled", True):
            continue
        includes = [str(value).strip() for value in rule.get("includeKeywords", []) if str(value).strip()]
        excludes = [str(value).strip() for value in rule.get("excludeKeywords", []) if str(value).strip()]
        matched = [value for value in includes if value.lower() in source]
        blocked = [value for value in excludes if value.lower() in source]
        if not matched or blocked:
            continue
        priority = int(rule.get("priority", 3) or 3)
        score = min(.98, .28 + len(matched) / max(2, len(includes)) * .5 + priority * .04)
        scored.append({"criterionId": rule.get("criterionId"), "criterionName": rule.get("criterionName"), "evidenceName": rule.get("evidenceName"), "category": rule.get("category", ""), "confidence": round(score, 2), "method": "expert_rule", "matchedKeywords": matched, "reason": f"전문가 규칙 키워드 {', '.join(matched[:5])} 일치"})
    return sorted(scored, key=lambda item: item["confidence"], reverse=True)


def heuristic_match_document(filename: str, extracted_text: str) -> dict | None:
    source_tokens = token_set(f"{filename} {extracted_text[:3000]}")
    best = None
    best_score = 0.0
    for candidate in evidence_candidates():
        candidate_tokens = token_set(f"{candidate['criterionName']} {candidate['category']} {candidate['evidenceName']}")
        for existing in list_uploaded_documents(candidate["criterionId"]):
            if existing.get("evidenceName") == candidate["evidenceName"]:
                candidate_tokens |= token_set(f"{existing.get('fileName', '')} {existing.get('textPreview', '')}")
        if not candidate_tokens:
            continue
        overlap = source_tokens & candidate_tokens
        score = len(overlap) / max(4, len(candidate_tokens))
        if score > best_score:
            best = candidate
            best_score = score
    if best and best_score >= 0.18:
        return {**best, "confidence": round(min(best_score, 0.95), 2), "method": "heuristic"}
    return None


def parse_llm_json(content: str) -> dict | None:
    if not content:
        return None
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def llm_match_document(filename: str, extracted_text: str) -> dict | None:
    candidates = evidence_candidates()
    task = """
업로드 문서가 어떤 ODA 평가 기준의 필수 증빙 항목에 해당하는지 분류하세요.
반드시 JSON 객체만 반환하세요.
형식: {"matched": true|false, "criterionId": "...", "evidenceName": "...", "confidence": 0.0~1.0, "reason": "..."}
적절한 항목이 없거나 확신이 낮으면 {"matched": false, "reason": "..."}를 반환하세요.
"""
    context = {
        "fileName": filename,
        "textPreview": extracted_text[:5000],
        "candidates": candidates,
    }
    result = OPENROUTER.request_chat_completion(OPENROUTER.build_messages(task, context))
    parsed = parse_llm_json(result.get("content", "")) if result.get("ok") else None
    if not parsed or not parsed.get("matched"):
        return None
    criterion_id = parsed.get("criterionId")
    evidence_name = parsed.get("evidenceName")
    candidate = next((item for item in candidates if item["criterionId"] == criterion_id and item["evidenceName"] == evidence_name), None)
    if not candidate:
        return None
    return {
        **candidate,
        "confidence": float(parsed.get("confidence", 0.6) or 0.6),
        "method": "llm",
        "reason": parsed.get("reason", ""),
    }


def semantic_llm_match_document(filename: str, extracted_text: str, metadata: dict) -> dict | None:
    config = intake_rules_payload()
    slot_rules = [item for item in config.get("slotRules", []) if item.get("enabled", True)]
    task = """ODA 평가 전문가가 작성한 자연어 슬롯 기준에 따라 문서의 실제 의미와 평가 활용 목적을 판정하세요.
파일명 단어 일치가 아니라 본문, 추출 메타데이터, 배정 기준, 배정하지 않는 조건을 종합하세요.
가능성이 높은 순서대로 최대 4개 후보를 반환하고, 문서의 구체적인 근거와 반대 근거를 설명하세요.
확신할 수 없으면 candidates를 비우세요. JSON 객체만 반환하세요.
형식: {"candidates":[{"criterionId":"...","evidenceName":"...","confidence":0.0,"reason":"...","counterEvidence":"..."}],"reviewReason":"..."}"""
    context = {"fileName": filename, "documentMetadata": metadata, "text": extracted_text[:14000], "expertAllocationPolicy": config.get("allocationPolicy", {}), "expertSlotGuidance": slot_rules}
    result = OPENROUTER.request_chat_completion(OPENROUTER.build_messages(task, context))
    parsed = parse_llm_json(result.get("content", "")) if result.get("ok") else None
    if not parsed or not isinstance(parsed.get("candidates"), list):
        return None
    valid = {(item["criterionId"], item["evidenceName"]): item for item in slot_rules}
    candidates = []
    for item in parsed["candidates"][:4]:
        rule = valid.get((item.get("criterionId"), item.get("evidenceName")))
        if not rule:
            continue
        candidates.append({"criterionId": rule["criterionId"], "criterionName": rule["criterionName"], "evidenceName": rule["evidenceName"], "category": rule.get("category", ""), "confidence": max(0, min(1, float(item.get("confidence", 0) or 0))), "method": "llm_semantic", "reason": item.get("reason", ""), "counterEvidence": item.get("counterEvidence", "")})
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    if not candidates:
        return None
    best = dict(candidates[0])
    best["alternatives"] = candidates[1:]
    best["margin"] = round(best["confidence"] - (candidates[1]["confidence"] if len(candidates) > 1 else 0), 2)
    best["reviewReason"] = parsed.get("reviewReason", "")
    best["policyVersion"] = config.get("version", 1)
    return best


def match_document_target(filename: str, extracted_text: str, metadata: dict) -> dict | None:
    return semantic_llm_match_document(filename, extracted_text, metadata)


def legacy_match_document_target(filename: str, extracted_text: str) -> dict | None:
    policy = intake_rules_payload().get("allocationPolicy", {})
    merged = _legacy_rule_match_candidates(filename, extracted_text)
    llm_candidate = llm_match_document(filename, extracted_text)
    if llm_candidate:
        existing = next((item for item in merged if item["criterionId"] == llm_candidate["criterionId"] and item["evidenceName"] == llm_candidate["evidenceName"]), None)
        if existing:
            existing["confidence"] = round(existing["confidence"] * float(policy.get("ruleWeight", .55)) + llm_candidate["confidence"] * float(policy.get("llmWeight", .45)), 2)
            existing["method"] = "expert_rule+llm"
            existing["reason"] += f" · LLM 교차확인: {llm_candidate.get('reason', '')}"
        else:
            merged.append(llm_candidate)
    if not merged:
        heuristic = heuristic_match_document(filename, extracted_text)
        if heuristic:
            merged.append(heuristic)
    merged.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    if not merged:
        return None
    best = dict(merged[0])
    best["alternatives"] = merged[1:int(policy.get("maxSlots", 4) or 4)]
    best["margin"] = round(best["confidence"] - (merged[1]["confidence"] if len(merged) > 1 else 0), 2)
    best["policyVersion"] = intake_rules_payload().get("version", 1)
    return best


def batch_upload_documents(files: list[dict]) -> dict:
    proposals = []
    auto_assigned = []
    shared_documents = []
    updated_criteria = set()
    for file_body in files:
        filename = safe_filename(file_body.get("fileName", "uploaded_file"))
        raw = base64.b64decode(file_body.get("contentBase64", ""))
        mime_type = file_body.get("mimeType", "application/octet-stream")
        extracted_text, _ = extract_text(raw, filename, mime_type)
        analysis_metadata = extract_document_metadata(filename, extracted_text, mime_type)
        target = match_document_target(filename, extracted_text, analysis_metadata)
        confidence = float((target or {}).get("confidence", 0) or 0)
        policy = intake_rules_payload().get("allocationPolicy", {})
        can_auto_assign = bool(target and confidence >= float(policy.get("autoAssignThreshold", .82)) and float(target.get("margin", 1)) >= float(policy.get("minimumMargin", .12)))
        allocation_trace = {"policyVersion": target.get("policyVersion") if target else intake_rules_payload().get("version"), "decision": "auto_assigned" if can_auto_assign else "expert_review", "suggestion": target}
        file_body = {**file_body, "analysisMetadata": analysis_metadata, "allocationTrace": allocation_trace}
        if can_auto_assign:
            document = save_uploaded_document(
                target["criterionId"],
                {
                    **file_body,
                    "fileName": filename,
                    "mimeType": mime_type,
                    "evidenceName": target["evidenceName"],
                    "analysisMetadata": analysis_metadata,
                    "allocationTrace": allocation_trace,
                },
            )
            document["matchStatus"] = "auto_assigned"
            document["suggestedMatch"] = target
            persist_document_metadata(target["criterionId"], document)
            auto_assigned.append(document)
            updated_criteria.add(target["criterionId"])
            shared = apply_shared_evidence(document)
            shared_documents.extend(shared)
            updated_criteria.update(item.get("criterionId", "") for item in shared)
            continue
        document = save_uploaded_document(
            "_pending",
            {
                **file_body,
                "fileName": filename,
                "mimeType": mime_type,
                "evidenceName": target["evidenceName"] if target else "분류 제안 필요",
            },
        )
        document["matchStatus"] = "proposal_ready" if target else "proposal_unmatched"
        document["suggestedMatch"] = target
        persist_document_metadata("_pending", document)
        proposals.append(document)

    evaluations = regenerate_affected_criteria({item for item in updated_criteria if item})
    return {
        "proposals": proposals,
        "autoAssigned": auto_assigned,
        "sharedDocuments": shared_documents,
        "evaluations": evaluations,
        "dashboard": dashboard_payload(),
    }


def move_staged_document(source_bucket: str, document_id: str, criterion_id: str, evidence_name: str, status: str) -> dict:
    criterion = find_criterion(criterion_id)
    if not criterion:
        raise ValueError("Criterion not found")
    document, meta_path = find_uploaded_document(source_bucket, document_id)
    if not document:
        raise ValueError("Document not found")
    target_upload_dir = UPLOAD_DIR / criterion_id
    target_text_dir = TEXT_DIR / criterion_id
    target_upload_dir.mkdir(parents=True, exist_ok=True)
    target_text_dir.mkdir(parents=True, exist_ok=True)

    raw_path = Path(document.get("rawPath", ""))
    text_path = Path(document.get("textPath", ""))
    if raw_path.exists():
        new_raw_path = target_upload_dir / raw_path.name
        raw_path.replace(new_raw_path)
        document["rawPath"] = str(new_raw_path)
    if text_path.exists():
        new_text_path = target_text_dir / text_path.name
        text_path.replace(new_text_path)
        document["textPath"] = str(new_text_path)
    if meta_path:
        meta_path.unlink(missing_ok=True)

    document.update(
        {
            "criterionId": criterion_id,
            "evidenceName": evidence_name,
            "matchStatus": status,
            "assignedAt": now_label(),
        }
    )
    document.pop("suggestedMatch", None)
    persist_document_metadata(criterion_id, document)
    return document


def confirm_batch_documents(assignments: list[dict]) -> dict:
    assigned = []
    shared_documents = []
    updated_criteria = set()
    for assignment in assignments:
        criterion_id = assignment.get("criterionId", "")
        evidence_name = assignment.get("evidenceName", "").strip()
        document_id = assignment.get("documentId", "")
        if not criterion_id or not evidence_name or not document_id:
            continue
        document = move_staged_document("_pending", document_id, criterion_id, evidence_name, "confirmed_assigned")
        assigned.append(document)
        updated_criteria.add(criterion_id)
        shared = apply_shared_evidence(document)
        shared_documents.extend(shared)
        updated_criteria.update(item.get("criterionId", "") for item in shared)

    evaluations = regenerate_affected_criteria({item for item in updated_criteria if item})
    return {"assigned": assigned, "sharedDocuments": shared_documents, "evaluations": evaluations, "dashboard": dashboard_payload()}


def assign_unmatched_document(document_id: str, criterion_id: str, evidence_name: str) -> dict:
    document = move_staged_document("_unmatched", document_id, criterion_id, evidence_name, "manual_assigned")
    shared_documents = apply_shared_evidence(document)
    affected = {criterion_id, *(item.get("criterionId", "") for item in shared_documents)}
    evaluations = regenerate_affected_criteria({item for item in affected if item})
    return {
        "document": document,
        "sharedDocuments": shared_documents,
        "evaluationResult": evaluations.get(criterion_id),
        "evaluations": evaluations,
        "dashboard": dashboard_payload(),
    }


def sync_project_overview_to_relevance(overview: dict, extracted_text: str, extraction_method: str) -> dict:
    document_id = "project_overview"
    criterion_id = "relevance"
    criterion_upload_dir = UPLOAD_DIR / criterion_id
    criterion_text_dir = TEXT_DIR / criterion_id
    criterion_upload_dir.mkdir(parents=True, exist_ok=True)
    criterion_text_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(overview["path"])
    raw_path = criterion_upload_dir / f"{document_id}_{overview['name']}"
    if source_path.exists():
        raw_path.write_bytes(source_path.read_bytes())
    text_path = criterion_text_dir / f"{document_id}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")

    remove_document_metadata_by_evidence(criterion_id, PROJECT_OVERVIEW_EVIDENCE_NAME)
    document = {
        "id": document_id,
        "criterionId": criterion_id,
        "evidenceName": PROJECT_OVERVIEW_EVIDENCE_NAME,
        "fileName": overview["name"],
        "mimeType": mimetypes.guess_type(overview["name"])[0] or "application/octet-stream",
        "size": overview["size"],
        "rawPath": str(raw_path),
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
        "uploadedAt": now_label(),
        "source": "project_overview",
    }
    persist_document_metadata(criterion_id, document)
    return document


def ensure_project_overview_evidence_synced() -> None:
    overview = current_project_overview()
    if overview.get("source") != "uploaded" or not overview.get("exists"):
        return
    for document in list_uploaded_documents("relevance"):
        if document.get("evidenceName") == PROJECT_OVERVIEW_EVIDENCE_NAME and document.get("fileName") == overview.get("name"):
            return
    text_path_value = overview.get("textPath")
    text_path = Path(text_path_value) if text_path_value else None
    if text_path and text_path.exists():
        extracted_text = text_path.read_text(encoding="utf-8")
    else:
        raw_path = Path(overview["path"])
        raw = raw_path.read_bytes() if raw_path.exists() else b""
        mime_type = mimetypes.guess_type(overview.get("name", ""))[0] or "application/octet-stream"
        extracted_text, extraction_method = extract_text(raw, overview.get("name", raw_path.name), mime_type)
        overview["extractionMethod"] = extraction_method
    sync_project_overview_to_relevance(
        overview,
        extracted_text,
        overview.get("extractionMethod", "synced_project_overview"),
    )

