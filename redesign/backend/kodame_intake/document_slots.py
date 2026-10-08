from __future__ import annotations

DOCUMENT_SLOTS = {
    "relevance": {
        "name": "적절성",
        "need": 10,
        "slots": [
            ("relevance-baseline", "예비/기획조사 결과보고서 (Baseline)"),
            ("relevance-demand", "수혜자·이해관계자 수요조사서"),
            ("relevance-pcp", "사업개요서 / 사업요청서 (PCP)"),
            ("relevance-policy", "협력국 국가개발전략·부문 정책"),
            ("relevance-alignment", "우선순위·정책 부합성 증빙"),
        ],
    },
    "coherence": {
        "name": "일관성",
        "need": 9,
        "slots": [
            ("coherence-cps", "공여기관 협력전략 (CPS)"),
            ("coherence-sdgs", "국제개발목표(SDGs) 연계 근거"),
            ("coherence-duplication", "유사·중복 사업 검토 자료"),
            ("coherence-coordination", "현지 정부·타 공여기관 협업 문서"),
        ],
    },
    "effectiveness": {
        "name": "효과성",
        "need": 10,
        "slots": [
            ("effectiveness-pdm", "사업설계매트릭스 (PDM)"),
            ("effectiveness-results", "성과지표 실적자료"),
            ("effectiveness-baseline", "기준선(Baseline) 조사자료"),
            ("effectiveness-endline", "종료선(Endline) 조사자료"),
            ("effectiveness-equity", "소외계층 포용·형평성 자료"),
            ("effectiveness-outputs", "산출물·교육성과 증빙"),
        ],
    },
    "efficiency": {
        "name": "효율성",
        "need": 7,
        "slots": [
            ("efficiency-budget", "예산 집행 내역"),
            ("efficiency-schedule", "사업 일정·공정 자료"),
            ("efficiency-procurement", "조달 내역·계약 문서"),
            ("efficiency-value", "투입 대비 산출 분석"),
        ],
    },
    "impact": {
        "name": "영향",
        "need": 8,
        "slots": [
            ("impact-longterm", "중장기 성과 변화 자료"),
            ("impact-tracking", "수혜자 변화 추적 자료"),
            ("impact-policy", "제도·정책 반영 근거"),
            ("impact-spillover", "파급효과·사례 자료"),
        ],
    },
    "sustainability": {
        "name": "지속가능성",
        "need": 6,
        "slots": [
            ("sustainability-operation", "운영·유지관리 계획"),
            ("sustainability-capacity", "현지 인력 교육·인수인계 자료"),
            ("sustainability-finance", "재정 자립·예산 확보 근거"),
            ("sustainability-institution", "제도화·거버넌스 자료"),
        ],
    },
}


def _choose_slot_details(
    criterion: str, file_name: str, document_type: str = "", context: str = "",
) -> tuple[str, str, float, list[str]]:
    file_text = file_name.lower()
    type_text = document_type.lower()
    context_text = context.lower()
    rules = {
        "relevance": [
            (("사전타당", "사전조사", "기초선", "baseline"), "relevance-baseline"),
            (("수요조사", "요구조사", "이해관계자 수요", "만족도"), "relevance-demand"),
            (("사업계획", "사업개요", "사업요청", "pcp", "concept paper"), "relevance-pcp"),
            (("국가개발", "부문정책", "정책", "전략", "법령"), "relevance-policy"),
        ],
        "coherence": [
            (("cps", "국가협력전략", "협력전략"), "coherence-cps"),
            (("sdg", "지속가능발전목표", "개발목표"), "coherence-sdgs"),
            (("중복", "유사사업", "타 사업", "비교"), "coherence-duplication"),
            (("mou", "업무협약", "협의록", "협업", "조정", "공문", "승인"), "coherence-coordination"),
        ],
        "effectiveness": [
            (("pdm", "논리모형", "성과관리 프레임워크"), "effectiveness-pdm"),
            (("성과지표", "실적보고", "모니터링", "달성도", "성과측정"), "effectiveness-results"),
            (("기준선", "baseline", "사전측정"), "effectiveness-baseline"),
            (("종료선", "endline", "사후측정", "추적조사", "취업률"), "effectiveness-endline"),
            (("소외", "형평", "취약", "젠더", "여성", "장애"), "effectiveness-equity"),
            (("교육결과", "수료", "교재", "커리큘럼", "교육과정", "산출물"), "effectiveness-outputs"),
        ],
        "efficiency": [
            (("예산", "집행", "재무", "정산", "지출", "원가"), "efficiency-budget"),
            (("일정", "공정", "추진계획", "월간", "연간계획", "공정률"), "efficiency-schedule"),
            (("기자재", "검수", "조달", "계약", "입찰", "납품"), "efficiency-procurement"),
            (("비용효과", "투입 대비", "단가", "경제성", "가성비"), "efficiency-value"),
        ],
        "impact": [
            (("중장기", "장기성과", "사회경제", "영향평가"), "impact-longterm"),
            (("추적", "패널", "동문", "취업", "수혜자 변화"), "impact-tracking"),
            (("정책", "승인", "제도", "법령", "국가표준"), "impact-policy"),
            (("사례", "확산", "파급", "복제", "모델 확산"), "impact-spillover"),
        ],
        "sustainability": [
            (("운영", "유지보수", "유지관리", "인수인계", "매뉴얼"), "sustainability-operation"),
            (("역량강화", "교원", "강사", "교과", "강의", "워크샵", "연수"), "sustainability-capacity"),
            (("운영예산", "재정", "자립", "비용회수", "예산 확보"), "sustainability-finance"),
            (("제도화", "거버넌스", "조직", "위원회", "학칙", "정규과정"), "sustainability-institution"),
        ],
    }
    defaults = {
        "relevance": "relevance-alignment",
        "coherence": "coherence-duplication",
        "effectiveness": "effectiveness-outputs",
        "efficiency": "efficiency-value",
        "impact": "impact-longterm",
        "sustainability": "sustainability-institution",
    }
    slot_id = defaults[criterion]
    best_score = 0
    best_hits: list[str] = []
    for needles, candidate in rules.get(criterion, []):
        hits = [needle for needle in needles if needle in file_text or needle in type_text or needle in context_text]
        score = sum(
            4 if needle in file_text else 2 if needle in type_text else 1
            for needle in hits
        )
        if score > best_score:
            slot_id = candidate
            best_score = score
            best_hits = hits
    title = next(title for sid, title in DOCUMENT_SLOTS[criterion]["slots"] if sid == slot_id)
    confidence = min(0.95, 0.62 + best_score * 0.035) if best_score else 0.6
    return slot_id, title, confidence, best_hits


def choose_slot(criterion: str, file_name: str, document_type: str = "", context: str = "") -> tuple[str, str]:
    slot_id, title, _, _ = _choose_slot_details(criterion, file_name, document_type, context)
    return slot_id, title


def document_slot_matches(file_name: str, analysis: dict) -> list[dict]:
    from .document_classification import VERSION, is_project_plan, pdm_slots
    classification = analysis.get("content_classification") or {}
    if classification.get("version") == VERSION:
        selected = {item["slot_id"].split("-", 1)[0]: dict(item)
                    for item in classification.get("slot_matches", []) if item.get("confidence", 0) >= 0.45}
        # These are persisted semantic roles, not filename/keyword guesses.
        for active, criterion, slot_id in (
            (is_project_plan(analysis), "relevance", "relevance-pcp"),
            (bool(pdm_slots(analysis)), "effectiveness", "effectiveness-pdm"),
        ):
            if active:
                if selected.get(criterion, {}).get("slot_id") != slot_id:
                    selected[criterion] = {"slot_id": slot_id, "confidence": classification.get("role_confidence", 0),
                                           "reason": classification.get("reason", "")}
        result = []
        for criterion, item in selected.items():
            meta = DOCUMENT_SLOTS.get(criterion)
            if not meta:
                continue
            title = dict(meta["slots"]).get(item["slot_id"])
            if title:
                result.append({"criterion": criterion, "criterion_name": meta["name"],
                               "slot_id": item["slot_id"], "slot_title": title,
                               "confidence": item["confidence"], "rationale": "LLM 본문 분석: " + item["reason"]})
        return result
    lowered_name = file_name.lower()
    if any(token in lowered_name for token in (
        "readme", "업로드_안내", "자료요청", "메일초안", "google_drive_생성", "자료없음"
    )):
        return []
    criteria = [item for item in analysis.get("dac_criteria", []) if item in DOCUMENT_SLOTS]
    if not criteria:
        criteria = ["effectiveness"] if any(word in file_name for word in ("교육", "자료", "README")) else ["relevance"]
    context_parts = [
        str(analysis.get("summary", "")),
        " ".join(map(str, analysis.get("oda_categories", []) or [])),
        " ".join(map(str, analysis.get("organizations", []) or [])),
    ]
    for match in analysis.get("section_matches", []) or []:
        if isinstance(match, dict):
            context_parts.extend((str(match.get("section_title", "")), str(match.get("rationale", ""))))
    context = " ".join(context_parts)
    result = []
    for criterion in dict.fromkeys(criteria):
        slot_id, slot_title, confidence, hits = _choose_slot_details(
            criterion, file_name, str(analysis.get("document_type", "")), context,
        )
        result.append({
            "criterion": criterion,
            "criterion_name": DOCUMENT_SLOTS[criterion]["name"],
            "slot_id": slot_id,
            "slot_title": slot_title,
            "confidence": round(confidence, 2),
            "rationale": (
                f"문서명·유형·요약에서 {', '.join(hits[:5])} 신호를 확인해 배정"
                if hits else f"{DOCUMENT_SLOTS[criterion]['name']} 관련 문서의 기본 보완 슬롯으로 배정"
            ),
        })
    return result
