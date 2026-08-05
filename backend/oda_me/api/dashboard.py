from __future__ import annotations

from ..core import *

def dashboard_insights(criteria: list[dict], unmatched: list[dict], pending: list[dict], overall: dict) -> dict:
    grade_criteria = [item for item in criteria if item.get("id") != "impact"]
    total_required = sum(len(item.get("evidence", [])) for item in grade_criteria) or 1

    def evidence_slot_stats(criterion: dict) -> dict:
        required_names = [evidence.get("name", "") for evidence in criterion.get("evidence", []) if evidence.get("name")]
        filled_names = {
            document.get("evidenceName", "")
            for document in criterion.get("uploadedDocuments", [])
            if document.get("evidenceName", "") in required_names
        }
        required = len(required_names)
        filled = len(filled_names)
        return {
            "uploaded": filled,
            "required": required,
            "coverage": round(filled / max(1, required) * 100),
            "missing": [name for name in required_names if name not in filled_names],
        }

    def improvement_needs(criterion: dict, missing_slots: list[str], limit: int = 3) -> list[str]:
        needs: list[str] = []
        evaluation = criterion.get("evaluationResult") or {}

        def add_need(value: str | None) -> None:
            text = re.sub(r"^\s*(?:[-•ㅇ]|\d+(?:\.\d+)*\.?)\s*", "", str(value or "")).strip()
            text = re.sub(r"^(?:증빙공백|핵심사유|보완 필요사항)\s*[:：]\s*", "", text).strip()
            if text.endswith("?") or re.search(r"인가\??$|는가\??$|하였는가\??$", text):
                return
            if text and text not in needs:
                needs.append(short_text(text, 130))

        for need in evaluation.get("improvementNeeds", []) or []:
            add_need(need)
            if len(needs) >= limit:
                return needs[:limit]

        candidate_lines = plain_lines(evaluation.get("summary"))
        for section in evaluation.get("sections", []) or []:
            candidate_lines.extend(plain_lines(section.get("body")))

        priority_pattern = re.compile(r"증빙공백|추가\s*확인\s*필요|추가\s*정보\s*필요|미확인|부족|미비|누락", re.IGNORECASE)
        for line in candidate_lines:
            if priority_pattern.search(line):
                add_need(line)
            if len(needs) >= limit:
                return needs[:limit]

        for name in missing_slots:
            add_need(f"{name} 추가 업로드 필요")
            if len(needs) >= limit:
                return needs[:limit]

        if criterion_score(criterion) < 4:
            for section in evaluation.get("sections", []) or []:
                body = str(section.get("body") or "").strip()
                if body:
                    add_need(body)
                if len(needs) >= limit:
                    break
        return needs[:limit]

    total_uploaded = sum(evidence_slot_stats(item)["uploaded"] for item in grade_criteria)
    total_assigned_documents = sum(len(item.get("uploadedDocuments", [])) for item in grade_criteria)
    def evaluation_draft_score(criterion: dict) -> int:
        evaluation = criterion.get("evaluationResult") or {}
        if evaluation.get("status") in {None, "waiting"} and not evaluation.get("score"):
            return 0
        score = 0
        if evaluation.get("score"):
            score += 15
        summary = str(evaluation.get("summary") or "").strip()
        if summary and not re.search(r"자료 업로드 전|평가 필수 증빙", summary):
            score += 15
        if evaluation.get("sections"):
            score += 10
        return min(40, score)

    def judgement_readiness_score(criterion: dict, slot_stats: dict, needs: list[str]) -> int:
        draft_score = evaluation_draft_score(criterion)
        evidence_score = round(slot_stats.get("coverage", 0) * 0.45)
        score_component = max(0, (criterion_score(criterion) - 1) * 5)
        base_score = draft_score + evidence_score + score_component
        need_penalty = min(40, len(needs) * 12)
        severe_need_pattern = re.compile(r"증빙공백|추가\s*확인|미확인|누락|부족|미비", re.IGNORECASE)
        if any(severe_need_pattern.search(str(need)) for need in needs):
            need_penalty = min(45, need_penalty + 5)
        return max(0, min(100, base_score - need_penalty))

    evaluated = [item for item in grade_criteria if evaluation_draft_score(item) > 0]
    report_state = read_report_editor_state()
    evidence_rate = min(100, round(total_uploaded / total_required * 100))
    score_rate = round((overall.get("score", 0) / max(1, overall.get("maxScore", 20))) * 100)
    unresolved_documents = len(unmatched) + len(pending)
    managed_documents = total_assigned_documents + unresolved_documents
    classification_rate = 0 if managed_documents == 0 else round((managed_documents - unresolved_documents) / managed_documents * 100)

    criterion_cards = []
    for item in grade_criteria:
        slot_stats = evidence_slot_stats(item)
        required = slot_stats["required"]
        uploaded = slot_stats["uploaded"]
        coverage = slot_stats["coverage"]
        evaluation = item.get("evaluationResult") or {}
        score = criterion_score(item)
        gaps = slot_stats["missing"][:3]
        needs = improvement_needs(item, slot_stats["missing"])
        judgement_readiness = judgement_readiness_score(item, slot_stats, needs)
        criterion_cards.append({
            "id": item.get("id"),
            "name": criterion_label(item),
            "score": score,
            "target": item.get("targetScore4", 4),
            "uploaded": uploaded,
            "required": required,
            "coverage": coverage,
            "judgementReadiness": judgement_readiness,
            "status": item.get("scoreStatus", "대기"),
            "evaluationStatus": evaluation.get("status", "waiting"),
            "gapSamples": gaps,
            "improvementNeeds": needs,
            "priority": (4 - score) * 10 + max(0, 70 - coverage) + (len(needs) * 8),
        })
    evaluation_rate = round(sum(item["judgementReadiness"] for item in criterion_cards) / max(1, len(criterion_cards)))
    remaining_needs = sum(len(item.get("improvementNeeds", [])) for item in criterion_cards)
    readiness = round((evidence_rate * 0.4) + (evaluation_rate * 0.25) + (score_rate * 0.2) + (classification_rate * 0.15))
    priority = sorted(criterion_cards, key=lambda item: item["priority"], reverse=True)[:3]
    missing_evidence = []
    for item in criterion_cards:
        criterion = find_criterion(item["id"]) or {}
        status = criterion.get("evidenceStatus") or {}
        for evidence in criterion.get("evidence", [])[:4]:
            name = evidence.get("name", "")
            if name and name not in status:
                missing_evidence.append({
                    "criterionId": item["id"],
                    "criterionName": item["name"],
                    "evidenceName": name,
                    "reason": "평가 판단 근거 보강 필요",
                })
    missing_evidence = missing_evidence[:6]

    def criterion_card(criterion_id: str) -> dict:
        return next((item for item in criterion_cards if item["id"] == criterion_id), {"uploaded": 0, "required": 1, "coverage": 0, "score": 1})

    achievement_ready = bool(report_state and any((section.get("id") == "achievement" and section.get("body")) for section in report_state.get("sections", [])))
    efficiency = criterion_card("efficiency")
    effectiveness = criterion_card("effectiveness")
    sustainability = criterion_card("sustainability")
    monitoring_checklist = [
        {
            "label": "사업개요/PDM 기준선",
            "criterionId": "relevance",
            "status": "ok" if (criterion_card("relevance")["uploaded"] > 0 and achievement_ready) else "gap",
            "detail": "사업목표, PDM, 성과지표 기준선 확인",
        },
        {
            "label": "성과 실적·MOV",
            "criterionId": "effectiveness",
            "status": "ok" if effectiveness["coverage"] >= 50 else "gap",
            "detail": f"효과성 증빙 {effectiveness['uploaded']}/{effectiveness['required']}건",
        },
        {
            "label": "예산·일정 집행",
            "criterionId": "efficiency",
            "status": "ok" if efficiency["coverage"] >= 50 else "gap",
            "detail": f"효율성 증빙 {efficiency['uploaded']}/{efficiency['required']}건",
        },
        {
            "label": "사후관리·지속가능성",
            "criterionId": "sustainability",
            "status": "ok" if sustainability["coverage"] >= 50 else "gap",
            "detail": f"지속가능성 증빙 {sustainability['uploaded']}/{sustainability['required']}건",
        },
    ]

    report_gates = [
        {
            "label": "자료수집",
            "status": "ok" if evidence_rate >= 60 else "gap",
            "statusLabel": "확보" if evidence_rate >= 60 else "보완 필요",
            "value": f"{evidence_rate}%",
            "progress": evidence_rate,
            "detail": f"필수 증빙 {total_uploaded}/{total_required}건 확보",
            "nextAction": "자료목록에서 비어 있는 자료 슬롯을 우선 업로드",
            "action": "references",
        },
        {
            "label": "기준별 판단",
            "status": "ok" if evaluation_rate >= 80 and remaining_needs == 0 else "gap",
            "statusLabel": "판단 완료" if evaluation_rate >= 80 and remaining_needs == 0 else "보완 필요",
            "value": f"{evaluation_rate}%",
            "progress": evaluation_rate,
            "detail": f"DAC 기준 판단 준비도 · 보완 필요 {remaining_needs}건 · 초안 {len(evaluated)}/{len(grade_criteria)}건",
            "nextAction": "평가기준 탭의 현재 보완 필요사항을 처리한 뒤 평가 초안을 재생성",
            "action": "criteria",
        },
        {
            "label": "자료 분류 정리",
            "status": "ok" if managed_documents > 0 and unresolved_documents == 0 else "gap",
            "statusLabel": "정리됨" if managed_documents > 0 and unresolved_documents == 0 else ("대기" if managed_documents == 0 else "정리 필요"),
            "value": "대기" if managed_documents == 0 else ("0건" if unresolved_documents == 0 else f"{unresolved_documents}건"),
            "progress": classification_rate,
            "detail": "업로드된 자료 없음 · 자료 업로드 후 기준/증빙 슬롯 배정" if managed_documents == 0 else f"미분류 {len(unmatched)}건 · 배정 대기 {len(pending)}건",
            "nextAction": "자료목록에서 업로드 자료를 평가기준별 증빙으로 매핑",
            "action": "references",
        },
        {
            "label": "제출 전 검토",
            "status": "gap" if overall.get("score", 0) < 14 or missing_evidence else "ok",
            "statusLabel": "검토 필요" if overall.get("score", 0) < 14 or missing_evidence else "제출 가능",
            "value": "보완" if missing_evidence else "가능",
            "progress": 100 if not missing_evidence and overall.get("score", 0) >= 14 else max(20, min(90, score_rate)),
            "detail": "점수·증빙·보고서 문장 정합성 검토 필요" if missing_evidence else "제출 전 핵심 요건 충족",
            "nextAction": "점수 산정 이유와 본문 판단 근거가 같은지 최종 대조",
            "action": "report",
        },
    ]

    actions = []
    if total_uploaded == 0:
        actions.append({"type": "evidence", "title": "기준별 핵심 증빙 업로드", "body": "각 DAC 기준의 필수 문서를 1건 이상 업로드하면 평가 초안 품질이 크게 올라갑니다."})
    for item in priority[:2]:
        actions.append({"type": "criterion", "title": f"{item['name']} 보완", "body": f"{item['uploaded']}/{item['required']}건 업로드 · 현재 {item['score']}점"})
    if pending or unmatched:
        actions.append({"type": "reference", "title": "미분류 문서 정리", "body": f"분류 대기 {len(pending)}건, 미분류 {len(unmatched)}건"})
    actions = actions[:5]
    if total_uploaded == 0:
        memo_headline = "증빙 기반 평가 착수 전 단계"
        memo_body = "현재 점수는 기본값에 가까우므로 등급 자체보다 기준별 핵심 증빙 확보가 우선임. 사업개요서, PDM, 성과자료, 예산·운영자료를 기준별로 매핑한 뒤 평가문장을 확정하는 절차가 필요함."
    elif overall.get("score", 0) < 10:
        memo_headline = "미흡 등급 개선을 위한 근거 보완 단계"
        memo_body = "낮은 점수 기준에 대해 증빙공백, 실제 이행성과, 외부 제약요인을 분리해 판단해야 함. 샘플 보고서처럼 평가질문별 근거와 한계를 함께 서술하는 방식이 적합함."
    else:
        memo_headline = "보고서 품질검토 대비 단계"
        memo_body = "점수와 본문 판단의 정합성, 환류과제의 실행가능성, 교훈의 체크리스트 전환 여부를 품질검토 관점에서 점검해야 함."

    return {
        "readiness": {
            "score": readiness,
            "label": "평가 패키지 준비도",
            "evidenceRate": evidence_rate,
            "evaluationRate": evaluation_rate,
            "scoreRate": score_rate,
            "classificationRate": classification_rate,
            "reportSaved": bool(report_state),
        },
        "evidence": {
            "uploaded": total_uploaded,
            "required": total_required,
            "coverage": evidence_rate,
            "unmatched": len(unmatched),
            "pending": len(pending),
        },
        "report": {
            "saved": bool(report_state),
            "updatedAt": (report_state or {}).get("updatedAt"),
            "sections": len([
                section for section in (report_state or {}).get("sections", [])
                if str(section.get("id") or section.get("sectionId") or "") in {
                    "cover",
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
                }
            ]),
        },
        "expertMemo": {
            "headline": memo_headline,
            "body": memo_body,
        },
        "priorityCriteria": priority,
        "criterionCards": criterion_cards,
        "nextActions": actions,
        "missingEvidence": missing_evidence,
        "monitoringChecklist": monitoring_checklist,
        "reportGates": report_gates,
    }


def dashboard_payload() -> dict:
    ensure_project_overview_evidence_synced()
    attach_uploaded_documents()
    apply_persisted_evaluations()
    grade_criteria = [item for item in CRITERIA if item.get("id") != "impact"]
    total_score = round(sum(float(item.get("currentScore4", 1) or 1) for item in grade_criteria), 1)
    koica_grade, gov_grade = overall_grade(total_score)
    unmatched = list_uploaded_documents("_unmatched")
    pending = list_uploaded_documents("_pending")
    overall = {
        "score": total_score,
        "maxScore": 20,
        "koicaGrade": koica_grade,
        "governmentGrade": gov_grade,
        "rule": "KOICA 평가등급은 영향 항목을 제외한 5개 기준의 질문별 평균점수 합산으로 산정하며, 각 기준 점수는 세부 평가질문 1~4점 평균을 소수 첫째 자리까지 반올림",
    }
    return {
        "project": project_payload(),
        "criteria": CRITERIA,
        "unmatchedDocuments": unmatched,
        "pendingDocuments": pending,
        "overall": overall,
        "insights": dashboard_insights(CRITERIA, unmatched, pending, overall),
        "updatedAt": now_label(),
        "chartA": {
            "title": "DAC 6대 기준 현재 평가점수",
            "description": "각 기준은 1~4점 척도로 표시되며, 미평가 항목은 1점으로 산정합니다.",
            "series": [
                {"name": "현재 평가점수", "key": "currentScore4", "color": "#52d5ff"},
            ],
        },
        "chartB": {
            "title": "DAC 6대 기준 목표 대비 현황",
            "description": "목표점수 4점 대비 현재 평가점수를 비교합니다.",
            "series": [
                {"name": "목표점수", "key": "targetScore4", "color": "#94a3b8"},
                {"name": "현재 평가점수", "key": "currentScore4", "color": "#0ea5e9"},
            ],
        },
    }


def project_overview_preview() -> dict:
    overview = current_project_overview()
    return {
        "project": project_payload(),
        "file": overview,
        "sections": [
            {"title": "문서 유형", "body": "2026-2027 CTS Seed1 국문 사업개요서 원본 HWP 파일입니다."},
            {"title": "임시 미리보기", "body": "현재 앱은 원본 파일을 연결한 상태이며, HWP 본문 렌더링은 PDF/HTML 변환 모듈 연동 후 제공할 수 있습니다."},
            {"title": "확인 항목", "body": "사업기간, 예산, 성과관리·평가 자동화 솔루션 범위, DAC 6대 기준 대응 자료를 원본에서 확인하세요."},
        ],
    }


def save_project_overview(body: dict) -> dict:
    filename = safe_filename(body.get("fileName", display_path_name(PROJECT_OVERVIEW_PATH)))
    mime_type = body.get("mimeType", "application/octet-stream")
    raw = base64.b64decode(body.get("contentBase64", ""))
    PROJECT_OVERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_path = PROJECT_OVERVIEW_UPLOAD_DIR / f"{timestamp}_{filename}"
    stored_path.write_bytes(raw)
    extracted_text, extraction_method = extract_text(raw, filename, mime_type)
    text_path = PROJECT_OVERVIEW_UPLOAD_DIR / f"{timestamp}_{Path(filename).stem}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")
    project_title = infer_project_title(extracted_text, filename) or "사업명 자료 기반 보수 작성"
    project_period, project_budget = extract_project_period_budget(extracted_text)
    overview = {
        "exists": True,
        "name": filename,
        "path": str(stored_path),
        "size": len(raw),
        "lastModified": now_label(),
        "downloadUrl": PROJECT["overviewUrl"],
        "source": "uploaded",
        "projectTitle": project_title,
        "projectPeriod": project_period or "기간 확인 필요",
        "projectBudget": project_budget or "사업비 확인 필요",
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
    }
    PROJECT_OVERVIEW_STATE_PATH.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    synced_document = sync_project_overview_to_relevance(overview, extracted_text, extraction_method)
    relevance = find_criterion("relevance")
    evaluation = generate_relevance_evaluation(synced_document) if relevance else None
    if relevance and evaluation:
        relevance["evaluationResult"] = evaluation
        if evaluation.get("score"):
            relevance["currentScore4"] = evaluation["score"]
            relevance["scoreStatus"] = "평가 완료"
        save_evaluation_result("relevance", evaluation)
    return {
        "saved": True,
        "project": project_payload(),
        "file": overview,
        "syncedDocument": synced_document,
        "evaluationResult": evaluation,
        "dashboard": dashboard_payload(),
        "message": "사업개요서 수정본이 업로드되었습니다.",
    }

