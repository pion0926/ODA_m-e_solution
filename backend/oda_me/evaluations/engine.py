from __future__ import annotations

from ..core import *
from ..clients.openrouter import OPENROUTER
from ..documents.evidence_store import attach_uploaded_documents, parse_llm_json
from ..documents.reference_corpus import build_evaluation_reference_corpus
from ..reports.context import criterion_label, plain_lines, short_text
from ..utils.common import find_criterion, now_label

def relevance_context(document: dict | None = None) -> dict:
    attach_uploaded_documents()
    uploaded_texts = []
    if (TEXT_DIR / "relevance").exists():
        for path in sorted((TEXT_DIR / "relevance").glob("*.txt")):
            uploaded_texts.append({"path": str(path), "text": path.read_text(encoding="utf-8")[:2000]})
    return {
        "project": project_payload(),
        "criterion": find_criterion("relevance"),
        "uploadedDocument": document,
        "uploadedTexts": uploaded_texts,
        "evaluationReferenceCorpus": build_evaluation_reference_corpus("relevance"),
        "commonScoringNotes": COMMON_SCORING_NOTES,
        "scoringRubric": RELEVANCE_SCORING,
        "requiredEvidence": RELEVANCE_EVIDENCE,
    }


def build_relevance_evaluation_sections(summary_text: str, criterion: dict) -> list[dict]:
    evidence_status = criterion.get("evidenceStatus") or {}
    evidence_items = criterion.get("evidence") or []

    def matching_evidence(pattern: str) -> list[str]:
        regex = re.compile(pattern, re.IGNORECASE)
        return [item.get("name", "") for item in evidence_items if regex.search(item.get("name", ""))]

    def missing_evidence(pattern: str) -> list[str]:
        return [name for name in matching_evidence(pattern) if name and name not in evidence_status]

    def relevant_lines(pattern: str, limit: int = 2) -> list[str]:
        regex = re.compile(pattern, re.IGNORECASE)
        blocked = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?)?\s*.+(?:인가|는가|하였는가)\??\s*$")
        selected = []
        for line in plain_lines(summary_text):
            if blocked.search(line):
                continue
            if len(line) < 70 and not re.search(r"확인|부합|반영|연계|수행|대응|필요|부족|미흡|누락|입증|검토|설계|구축", line):
                continue
            if regex.search(line):
                cleaned = re.sub(r"^\s*(?:[-•ㅇ]|\d+(?:\.\d+)*\.?)\s*", "", line).strip()
                if cleaned and cleaned not in selected:
                    selected.append(short_text(cleaned, 260))
            if len(selected) >= limit:
                break
        return selected

    def section_body(line_pattern: str, evidence_pattern: str, fallback: str) -> str:
        missing = missing_evidence(evidence_pattern)
        lines = relevant_lines(line_pattern)
        parts = []
        if lines:
            parts.extend(lines)
        if missing:
            parts.append(f"추가 확인 필요: {', '.join(missing[:4])}")
        if not parts:
            uploaded = matching_evidence(evidence_pattern)
            if uploaded and all(name in evidence_status for name in uploaded):
                parts.append("관련 필수 증빙은 업로드되어 있음. 평가결과 확정을 위해 문서 내 인용 위치와 판단 근거 반영 상태를 검토해야 함.")
            else:
                parts.append(fallback)
        return "\n".join(parts[:3])

    return [
        {
            "title": "수요 및 정책 부합성",
            "body": section_body(
                r"수요|기초조사|Baseline|CPS|CAS|국별협력|정책|전략|SDGs|부합",
                r"수요|기초조사|Baseline|CPS|CAS|국별협력|정책|전략|SDGs|협력국",
                "수요조사, 정책 부합성, KOICA 전략 매핑 근거 확인 필요",
            ),
        },
        {
            "title": "사업 설계 및 논리모형의 타당성",
            "body": section_body(
                r"PDM|Project Design Matrix|ToC|변화이론|문제나무|역할|MoU|ROD|협의의사록|논리모형|논리\s*체계",
                r"PDM|Project Design Matrix|ToC|변화이론|문제나무|역할|MoU|ROD|협의의사록",
                "PDM, ToC/문제나무, 이해관계자 역할분담 근거 확인 필요",
            ),
        },
        {
            "title": "상황 변화에 대한 대응성",
            "body": section_body(
                r"모니터링|Change Log|변경|JSC|운영위원회|상황\s*변화|대응|관리",
                r"모니터링|Change Log|변경|JSC|운영위원회",
                "모니터링 보고서, Change Log, 운영위원회 의사결정 회의록 확인 필요",
            ),
        },
    ]


def fallback_relevance_evaluation(document: dict | None = None, llm_result: dict | None = None) -> dict:
    attach_uploaded_documents()
    criterion = find_criterion("relevance") or {}
    uploaded_count = len(list((TEXT_DIR / "relevance").glob("*.txt"))) if (TEXT_DIR / "relevance").exists() else 0
    score = 2 if uploaded_count < 4 else 3
    if uploaded_count >= 10:
        score = 4
    summary = (
        f"현재 적절성 관련 업로드 문서는 {uploaded_count}건입니다. "
        "필수 증빙 전체가 완비되기 전까지 4점 상한 적용은 보류되며, 핵심 설계·수요·정책 부합성 자료 누락 시 최대 2점으로 제한될 수 있습니다."
    )
    summary_text = summary
    assessments = [
        {
            "questionId": f"q{index + 1}",
            "question": item.get("question", "적절성 평가질문"),
            "score": score,
            "finding": f"업로드 문서 {uploaded_count}건 기준으로 {score}점 수준으로 보수 산정됨.",
            "evidenceUsed": criterion_available_evidence(criterion)[:4],
            "evidenceGaps": criterion_missing_evidence(criterion)[index * 3 : (index + 1) * 3],
            "actionItems": [],
        }
        for index, item in enumerate(criterion.get("scoringRubric", []) or [])
    ]
    return {
        "status": "fallback",
        "score": average_question_score(assessments) if assessments else float(score),
        "scoreFormula": "questionAssessments 평균(소수 첫째 자리 반올림)",
        "summary": summary_text,
        "sections": build_relevance_evaluation_sections(summary_text, criterion),
        "questionAssessments": assessments,
        "model": OPENROUTER.model,
        "generatorVersion": CRITERION_EVALUATION_VERSION,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_relevance_evaluation(document: dict | None = None) -> dict:
    return generate_criterion_evaluation("relevance", document)


def criterion_context(criterion_id: str, document: dict | None = None) -> dict:
    attach_uploaded_documents()
    uploaded_texts = []
    text_dir = TEXT_DIR / criterion_id
    if text_dir.exists():
        for path in sorted(text_dir.glob("*.txt")):
            uploaded_texts.append({"path": str(path), "text": path.read_text(encoding="utf-8")[:2000]})
    criterion = find_criterion(criterion_id)
    return {
        "project": project_payload(),
        "criterion": criterion,
        "uploadedDocument": document,
        "uploadedTexts": uploaded_texts,
        "evaluationReferenceCorpus": build_evaluation_reference_corpus(criterion_id),
        "commonScoringNotes": COMMON_SCORING_NOTES,
        "scoringRubric": criterion.get("scoringRubric") if criterion else None,
        "requiredEvidence": criterion.get("evidenceGroups") if criterion else None,
    }


def fallback_coherence_evaluation(document: dict | None = None, llm_result: dict | None = None) -> dict:
    attach_uploaded_documents()
    criterion = find_criterion("coherence") or {}
    uploaded_count = len(list((TEXT_DIR / "coherence").glob("*.txt"))) if (TEXT_DIR / "coherence").exists() else 0
    score = 2 if uploaded_count < 3 else 3
    if uploaded_count >= 8:
        score = 4
    summary = (
        f"현재 일관성 관련 업로드 문서는 {uploaded_count}건입니다. "
        "타 공여 개입 매핑, 조정 회의록/MoU, 역할분담 문서, 세이프가드 자료가 모두 확인되기 전까지 4점 상한 적용은 보류됩니다."
    )
    missing = criterion_missing_evidence(criterion)
    assessments = [
        {
            "questionId": f"q{index + 1}",
            "question": item.get("question", "일관성 평가질문"),
            "score": score,
            "finding": f"업로드 문서 {uploaded_count}건 기준으로 {score}점 수준으로 보수 산정됨.",
            "evidenceUsed": criterion_available_evidence(criterion)[:4],
            "evidenceGaps": missing[index * 3 : (index + 1) * 3],
            "actionItems": [],
        }
        for index, item in enumerate(criterion.get("scoringRubric", []) or [])
    ]
    return {
        "status": "fallback",
        "score": average_question_score(assessments) if assessments else float(score),
        "scoreFormula": "questionAssessments 평균(소수 첫째 자리 반올림)",
        "summary": summary,
        "sections": [
            {
                "title": "내적 일관성",
                "body": "국내 정책, KOICA 타 사업, SDGs·인권·젠더·환경 등 국제규범 및 세이프가드 준수 근거를 기준으로 판단해야 함.\n"
                f"추가 확인 필요: {', '.join(missing[:4]) if missing else '문서 내 인용 위치 및 중복·충돌 여부 확인'}",
            },
            {
                "title": "외적 일관성",
                "body": "타 공여기관, 수원국 정부 및 현지 민간 개입과의 조정 회의록, MoU, 매핑 자료를 기준으로 중복 방지와 부가가치 창출 수준을 판단해야 함.\n"
                f"보완 조치: {', '.join(missing[4:8]) if len(missing) > 4 else '조정 회의록과 역할분담 근거의 실제 문장 반영 여부 검토'}",
            },
        ],
        "improvementNeeds": [f"{name} 확인 또는 업로드 필요" for name in missing[:6]],
        "questionAssessments": assessments,
        "model": OPENROUTER.model,
        "generatorVersion": CRITERION_EVALUATION_VERSION,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_coherence_evaluation(document: dict | None = None) -> dict:
    return generate_criterion_evaluation("coherence", document)


def fallback_generic_evaluation(criterion_id: str, document: dict | None = None, llm_result: dict | None = None) -> dict:
    attach_uploaded_documents()
    criterion = find_criterion(criterion_id) or {}
    criterion_name = criterion.get("name", criterion_id)
    text_dir = TEXT_DIR / criterion_id
    uploaded_count = len(list(text_dir.glob("*.txt"))) if text_dir.exists() else 0
    required_count = len(criterion.get("evidence", []))
    score = 1
    if uploaded_count:
        score = 2
    if required_count and uploaded_count >= max(2, required_count // 2):
        score = 3
    if required_count and uploaded_count >= required_count:
        score = 4

    summary = (
        f"현재 {criterion_name} 관련 업로드 문서는 {uploaded_count}건입니다. "
        f"필수 증빙 {required_count}건의 충족 여부와 문서 내용에 따라 1~4점 평가가 산정됩니다."
    )
    scoring = criterion.get("scoringRubric") or []
    missing = criterion_missing_evidence(criterion)
    available = criterion_available_evidence(criterion)
    sections = []
    assessments = []
    for index, item in enumerate(scoring):
        related_missing = missing[index * 3 : (index + 1) * 3] or missing[:3]
        related_available = available[index * 3 : (index + 1) * 3] or available[:3]
        body = [
            "업로드된 증빙자료와 1~4점 평가 기준표를 기준으로 보수적으로 판단해야 함.",
        ]
        if related_available:
            body.append(f"확인 증빙: {', '.join(related_available)}")
        if related_missing:
            body.append(f"증빙공백: {', '.join(related_missing)}")
            body.append(f"보완 조치: {related_missing[0]}를 업로드하거나 해당 내용이 포함된 기존 문서를 해당 슬롯에 연결")
        else:
            body.append("보완 조치: 문서 내 인용 위치, 수치 근거, 보고서 문장 반영 상태 확인")
        sections.append({"title": item.get("question", f"{criterion_name} 평가질문"), "body": "\n".join(body)})
        assessments.append(
            {
                "questionId": f"q{index + 1}",
                "question": item.get("question", f"{criterion_name} 평가질문"),
                "score": score,
                "finding": f"업로드 문서 {uploaded_count}건 기준으로 {score}점 수준으로 보수 산정됨.",
                "evidenceUsed": related_available[:4],
                "evidenceGaps": related_missing[:4],
                "actionItems": [f"{related_missing[0]} 확인 또는 업로드 필요"] if related_missing else [],
            }
        )
    return {
        "status": "fallback",
        "score": average_question_score(assessments) if assessments else float(score),
        "scoreFormula": "questionAssessments 평균(소수 첫째 자리 반올림)",
        "summary": summary,
        "sections": sections,
        "questionAssessments": assessments,
        "improvementNeeds": [f"{name} 확인 또는 업로드 필요" for name in missing[:6]],
        "model": OPENROUTER.model,
        "generatorVersion": CRITERION_EVALUATION_VERSION,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def criterion_missing_evidence(criterion: dict) -> list[str]:
    evidence_status = criterion.get("evidenceStatus") or {}
    return [
        evidence.get("name", "")
        for evidence in criterion.get("evidence", []) or []
        if evidence.get("name") and evidence.get("name") not in evidence_status
    ]


def criterion_available_evidence(criterion: dict) -> list[str]:
    evidence_status = criterion.get("evidenceStatus") or {}
    return [
        evidence.get("name", "")
        for evidence in criterion.get("evidence", []) or []
        if evidence.get("name") and evidence.get("name") in evidence_status
    ]


def build_structured_evaluation_task(base_prompt: str, criterion: dict) -> str:
    questions = [
        {"questionId": f"q{index + 1}", "question": item.get("question", ""), "levels": item.get("levels", [])}
        for index, item in enumerate(criterion.get("scoringRubric", []) or [])
    ]
    return f"""
{base_prompt}

[중요: 평가결과 출력 형식]
아래 JSON 객체만 반환하세요. 마크다운 코드블록, 별표, 추가 설명은 쓰지 마세요.
각 questionAssessments 항목은 반드시 scoringRubric의 평가질문 하나에 대응해야 합니다.
점수 산식은 각 평가질문별 1~4점 정수 점수를 먼저 산정하고, 최종 score는 questionAssessments[*].score의 산술평균으로 산정하세요.
평균이 소수이면 소수 첫째 자리까지 반올림하세요.

[점수 산정 원칙]
0. context.evaluationReferenceCorpus.documents에 포함된 배정 증빙 원문을 먼저 검토한 뒤 점수를 판단하세요. uploadedTexts는 보조 미리보기일 뿐이며, 원문 코퍼스의 evidenceName, fileName, text를 핵심 근거로 사용하세요.
1. 자료공백 자체를 자동 감점 사유로 삼지 마세요. 확인된 산출물·성과·운영성과가 충분하면 높은 점수를 줄 수 있습니다.
2. evidenceGaps와 actionItems는 "점수를 낮추는 벌점 목록"이 아니라, 최종 보고서 품질 보완사항으로만 관리하세요.
3. 확인된 긍정 성과를 반드시 점수 판단에 반영하세요. 예: 산출물/성과지표 달성, 목표 초과 달성, 수혜자 만족도, 현업적용도, 경제성/편익, 협력 파트너십, 사업 변경에 대한 유연한 대응, 후속 사후관리 노력.
4. 한계가 있더라도 성과 달성의 핵심 논리가 확인되면 3점 이상을 적극 검토하세요. 1~2점은 핵심 성과가 미달했거나, 부정적 영향이 성과를 실질적으로 훼손한 경우에 한정하세요.
5. 효과성은 "자료가 완벽한가"보다 산출물(output), 성과(outcome), 목표(goal)가 실제 달성되었는지를 우선 판단하세요.
6. 지속가능성은 예산·인력·유지보수 우려만 보지 말고, 역량강화, 권한부여, 현지 수용성, 사후관리사업, 제도 반영, 파트너십 등 지속가능성을 높이는 근거와 균형 있게 판단하세요.
7. 효율성은 지연/변경이 있더라도 비용 증액 억제, 대안 대비 편익, 예산 배분 적절성, 협력구조 개선 등 보완 성과가 있으면 반영하세요.
8. 일관성은 공식 RACI/MoU가 부족하더라도 실제 조정, UNICEF/정부/공여기관 협력, 유사사업 경험 활용 등 실행 근거가 확인되면 긍정적으로 반영하세요.
9. 증빙이 없거나 문서에서 확인되지 않은 내용은 단정하지 말고 evidenceGaps와 actionItems에 넣되, 확인된 성과까지 낮춰 평가하지 마세요.

{{
  "score": 1.0,
  "summary": "전체 판단 요약 3문장 이내",
  "questionAssessments": [
    {{
      "questionId": "q1",
      "question": "평가질문",
      "score": 1,
      "finding": "기준표에 따른 판단",
      "evidenceUsed": ["확인한 문서명 또는 증빙명"],
      "evidenceGaps": ["부족하거나 미확인인 증빙"],
      "actionItems": ["보완을 위해 사용자가 해야 할 구체 조치"]
    }}
  ],
  "improvementNeeds": ["현재 보완 필요사항을 사용자가 바로 실행할 수 있게 정리"],
  "scoreReason": "질문별 점수 평균에 따른 최종 점수 산정 이유 2문장 이내"
}}

[평가질문 매핑]
{json.dumps(questions, ensure_ascii=False, indent=2)}
"""


def clamp_score(value: object, default: int = 1) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = default
    return max(1, min(4, score))


def average_question_score(assessments: list[dict]) -> float:
    scores = [clamp_score(item.get("score"), 1) for item in assessments if isinstance(item, dict)]
    if not scores:
        return 1.0
    return round(sum(scores) / len(scores), 1)


def structured_evaluation_from_llm(criterion_id: str, document: dict | None, llm_result: dict | None) -> dict | None:
    if not llm_result or not llm_result.get("ok"):
        return None
    parsed = parse_llm_json(str(llm_result.get("content", "")))
    if not parsed:
        return None
    criterion = find_criterion(criterion_id) or {}
    rubric = criterion.get("scoringRubric", []) or []
    raw_assessments = parsed.get("questionAssessments")
    if not isinstance(raw_assessments, list):
        raw_assessments = []

    assessments = []
    sections = []
    for index, rubric_item in enumerate(rubric):
        fallback_question = rubric_item.get("question", f"{criterion_label(criterion)} 평가질문 {index + 1}")
        assessment = raw_assessments[index] if index < len(raw_assessments) and isinstance(raw_assessments[index], dict) else {}
        question = str(assessment.get("question") or fallback_question).strip()
        question_score = clamp_score(assessment.get("score"), clamp_score(parsed.get("score"), 1))
        evidence_used = [short_text(item, 90) for item in assessment.get("evidenceUsed", []) if str(item).strip()]
        evidence_gaps = [short_text(item, 100) for item in assessment.get("evidenceGaps", []) if str(item).strip()]
        action_items = [short_text(item, 120) for item in assessment.get("actionItems", []) if str(item).strip()]
        finding = short_text(str(assessment.get("finding") or "").strip(), 360)
        if not finding:
            finding = f"{question}에 대한 판단은 {question_score}점 수준으로 보수 산정됨."
        body_parts = [finding]
        if evidence_used:
            body_parts.append(f"확인 증빙: {', '.join(evidence_used[:4])}")
        if evidence_gaps:
            body_parts.append(f"증빙공백: {', '.join(evidence_gaps[:4])}")
        if action_items:
            body_parts.append(f"보완 조치: {', '.join(action_items[:3])}")
        assessments.append(
            {
                "questionId": str(assessment.get("questionId") or f"q{index + 1}"),
                "question": question,
                "score": question_score,
                "finding": finding,
                "evidenceUsed": evidence_used,
                "evidenceGaps": evidence_gaps,
                "actionItems": action_items,
            }
        )
        sections.append({"title": question, "body": "\n".join(body_parts)})

    parsed_needs = parsed.get("improvementNeeds") if isinstance(parsed.get("improvementNeeds"), list) else []
    improvement_needs = [short_text(item, 130) for item in parsed_needs if str(item).strip()]
    for assessment in assessments:
        for item in [*assessment.get("evidenceGaps", []), *assessment.get("actionItems", [])]:
            if item and item not in improvement_needs:
                improvement_needs.append(short_text(item, 130))
            if len(improvement_needs) >= 6:
                break
        if len(improvement_needs) >= 6:
            break
    for item in criterion_missing_evidence(criterion):
        need = f"{item} 확인 또는 업로드 필요"
        if need not in improvement_needs:
            improvement_needs.append(short_text(need, 130))
        if len(improvement_needs) >= 6:
            break

    if assessments:
        score = average_question_score(assessments)
    else:
        score = float(clamp_score(parsed.get("score"), 1))
    summary = str(parsed.get("summary") or parsed.get("scoreReason") or "").strip()
    if not summary:
        summary = f"{criterion_label(criterion)}는 업로드 증빙과 평가기준표에 따라 {score}/4점으로 산정됨."
    return {
        "status": "generated",
        "score": score,
        "scoreFormula": "questionAssessments 평균(소수 첫째 자리 반올림)",
        "summary": summary,
        "sections": sections,
        "questionAssessments": assessments,
        "improvementNeeds": improvement_needs[:6],
        "scoreReason": str(parsed.get("scoreReason") or "").strip(),
        "model": OPENROUTER.model,
        "generatorVersion": CRITERION_EVALUATION_VERSION,
        "llm": llm_result,
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_criterion_evaluation(criterion_id: str, document: dict | None = None) -> dict | None:
    attach_uploaded_documents()
    prompt = get_evaluation_prompt(criterion_id)
    if not prompt:
        return None
    context = relevance_context(document) if criterion_id == "relevance" else criterion_context(criterion_id, document)
    criterion = find_criterion(criterion_id) or {}
    messages = OPENROUTER.build_messages(build_structured_evaluation_task(prompt, criterion), context)
    llm_result = OPENROUTER.request_chat_completion(messages)
    structured = structured_evaluation_from_llm(criterion_id, document, llm_result)
    if structured:
        return clean_evaluation_result(structured)
    if criterion_id == "relevance":
        return clean_evaluation_result(fallback_relevance_evaluation(document, llm_result))
    if criterion_id == "coherence":
        return clean_evaluation_result(fallback_coherence_evaluation(document, llm_result))
    return clean_evaluation_result(fallback_generic_evaluation(criterion_id, document, llm_result))

