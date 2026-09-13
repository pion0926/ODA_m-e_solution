from __future__ import annotations

from datetime import datetime

from psycopg.types.json import Jsonb

from report_prompts import EDITOR_PART_REFERENCE_PIPELINES, EDITOR_REPORT_PARTS
from report_outline import canonical_narrative_outline_text

from .db import connection
from .evaluation_criteria import grade
from .hwpx_pipeline import SECTION_PIPELINES, validate_hwpx_pipeline_contracts
from .report_sources import is_report_evidence_document
from .report_text import sanitize_report_text


def _item_text(overview: dict, key: str, fallback: str = "확인 필요") -> str:
    return str((overview.get(key) or {}).get("text") or fallback)


def _latest_context() -> tuple[dict, list[dict], dict | None]:
    with connection() as conn:
        overview_row = conn.execute("SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1").fetchone()
        run = conn.execute("SELECT * FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1").fetchone()
        evaluations = conn.execute(
            "SELECT * FROM criterion_evaluations WHERE run_id=%s ORDER BY id", (run["id"],)
        ).fetchall() if run else []
    return (overview_row["overview"] if overview_row else {}), evaluations, run


def _questions(evaluations: list[dict]) -> list[dict]:
    return [question for row in evaluations for question in row["question_assessments"]]


def _criterion_body(row: dict | None) -> str:
    if not row:
        return "현재 자료에서 해당 평가기준의 확정 분석 결과를 확인하지 못하였다."
    parts = [row["summary"], row["score_reason"]]
    for index, question in enumerate(row["question_assessments"], 1):
        parts.append(f"{index}) {question['finding']}")
        limitations = question.get("limitations", [])
        if limitations:
            parts.append("다만 " + " ".join(limitations))
    return sanitize_report_text("\n\n".join(part for part in parts if part))


def bootstrap_contents() -> dict[str, str]:
    overview, evaluations, run = _latest_context()
    if not overview and not evaluations:
        return {str(part["id"]): "" for part in EDITOR_REPORT_PARTS}
    by_id = {row["criterion_id"]: row for row in evaluations}
    scored_total = round(sum(float(row["score"]) for row in evaluations), 1)
    result_grade, government_grade = grade(scored_total) if evaluations else ("-", "-")
    project = _item_text(overview, "project_name")
    background = _item_text(overview, "background")
    objective = _item_text(overview, "objective")
    activities = _item_text(overview, "activities")
    outputs = _item_text(overview, "outputs")
    outcomes = _item_text(overview, "outcomes")
    gaps = _item_text(overview, "evidence_gaps")
    all_questions = _questions(evaluations)
    limitations = list(dict.fromkeys(
        item for question in all_questions for item in question.get("evidence_gaps", [])
    ))
    actions = list(dict.fromkeys(
        item for question in all_questions for item in question.get("action_items", [])
    ))
    positives = list(dict.fromkeys(
        item for question in all_questions for item in question.get("positive_evidence", [])
    ))
    negatives = list(dict.fromkeys(
        item for question in all_questions for item in question.get("limitations", [])
    ))
    criterion_summary = "\n\n".join(
        f" ㅇ {row['criterion_name']}\n"
        f"- {float(row['score']):.1f}/4. {row['summary']}"
        for row in evaluations
    )
    grade_rows = "\n".join(
        f"{row['criterion_name']} {float(row['score']):.1f}/4 — {row['score_reason']}" for row in evaluations
    )
    matrix_rows = []
    for row in evaluations:
        for q in row["question_assessments"]:
            matrix_rows.append(
                f"- {row['criterion_name']} | {q['question']} | 판단점수 {q['score']}/4 | "
                f"자료원: 연결 문서 {len(q.get('evidence_document_ids', []))}건 | 방법: 문헌검토·교차검증"
            )
    today = datetime.now().strftime("%Y. %m")
    content = {
        "cover": f"{project}\n현재시점 문헌기반 평가보고서\n\n{today}\n\n평가책임자 자료 확인 필요\n평가수행기관 자료 확인 필요",
        "toc": "Ⅰ. 평가결과 요약\nⅡ. 대상사업 개요\nⅢ. 평가개요\nⅣ. 성과 달성도\nⅤ. 기준별 평가결과\nⅥ. 결론\n※ 쪽수는 HWPX 최종 조판 시 갱신",
        "notice": "평가 책임자: 확인 필요\n평가 기준일: 확인 필요\n본 보고서는 등록된 사업자료와 평가근거를 토대로 작성된 현재시점 문헌기반 평가 초안이다. 평가결과와 제언은 확인 가능한 자료 범위에 근거하며, 최종 제출 전 평가책임자와 관계기관의 사실확인 및 품질검토를 거쳐야 한다.",
        "grade": f"사업명: {project}\n{grade_rows}\n종합점수: {scored_total:.1f}/20\n종합 평가등급: {result_grade}\n국무조정실 평가등급: {government_grade}",
        "summary-ko": f"""(1) 대상사업개요

 ㅇ 사업 기본정보
- 사업명: {project}
- 대상국·지역: {_item_text(overview, 'country')} · {_item_text(overview, 'location')}

 ㅇ 추진배경 및 주요내용
- {objective}

(2) 평가개요

 ㅇ 평가 목적과 범위
- 현재 등록 자료를 기준으로 사업의 수행과 성과를 검토하고 후속 개선과제를 도출한다.

 ㅇ 평가 방법
- 사업계획·PDM·수행실적·성과자료를 문헌검토하고 자료 간 일치 여부를 교차대조한다.

 ㅇ 평가의 한계
- {gaps}

(3) 성과달성도

 ㅇ 주요 성과달성도
- {outcomes}

(4) 기준별 평가결과

{criterion_summary}

(5) 결론

 ㅇ 종합 결론
- 종합점수는 {scored_total:.1f}/20이며 종합 평가등급은 {result_grade}, 국무조정실 평가등급은 {government_grade}이다.

 ㅇ 작동요인
- 확인된 촉진요인을 후속 사업관리에서 유지한다.

 ㅇ 비작동요인
- 확인된 제약요인과 근거 공백을 후속 점검 대상으로 관리한다.

 ㅇ 환류과제 및 교훈
- {gaps}""",
        "project-background": background,
        "project-overview": f"사업명: {project}\n대상국·지역: {_item_text(overview, 'country')} · {_item_text(overview, 'location')}\n사업기간: {_item_text(overview, 'period')}\n총사업비: {_item_text(overview, 'budget')}\n지원기관: {_item_text(overview, 'donor')}\n수행기관: {_item_text(overview, 'implementer')}\n협력기관: {_item_text(overview, 'partner')}\n주요 수혜자: {_item_text(overview, 'beneficiaries')}\n주요 활동:\n{activities}",
        "pdm": f"상위목표\n우즈베키스탄 응급의료 서비스와 지역사회 대응역량 향상\n\n성과\n{outcomes}\n\n산출물\n{outputs}\n\n주요 활동\n{activities}\n\n지표·검증수단·가정은 등록된 최신 PDM과 연차별 성과자료를 기준으로 최종 표에 대조·확정해야 한다.",
        "eval-purpose": f"본 평가는 {project}의 현재시점에서 계획 대비 산출물과 성과 달성 수준을 확인하고, OECD DAC 기준에 따라 적절성·일관성·효과성·효율성·지속가능성을 분석하는 데 목적이 있다. 평가범위는 현재 등록된 사업기간과 사업자료이며, 결과는 후속 운영과 유사 ODA 사업 설계·관리를 위한 환류자료로 활용한다.",
        "eval-matrix": "평가기준 | 평가질문 | 판단지표 | 자료출처 | 분석방법\n" + "\n".join(matrix_rows),
        "eval-methods": "평가는 사업계획서, PDM, 연차별 자체평가보고서, 기자재 검수자료, 교원역량 강화자료, 수혜자 만족도 자료 등 등록 문서를 대상으로 문헌검토를 수행하였다. 문서별 요약과 원문 근거를 평가질문에 연결하고, 동일 사실은 복수 자료로 교차검증하였다. 현재 자료에서 수행이 입증되지 않은 인터뷰·현지조사·추가 설문은 실제 수행 사실로 간주하지 않았다.",
        "eval-limitations": "본 평가는 현재 등록된 자료를 중심으로 수행되어 다음 한계가 있다.\n- " + "\n- ".join(limitations or [gaps]) + "\n이러한 한계는 관련 판단을 보수적으로 해석하고 후속 추적조사를 제안하는 방식으로 완화하였다.",
        "eval-team": "평가 초안은 KODAME의 문서 교차분석과 평가기준별 검토를 통해 작성되었다. 최종 보고서에는 평가책임자, 분야전문가, 자료분석 담당자, 품질관리 담당자의 성명·소속·역할과 검토 절차를 확정하여 반영해야 한다.",
        "achievement": f"주요 산출물 달성\n{outputs}\n\n성과 달성 및 전망\n{outcomes}\n\n등록 자료에서는 학과 개설, Job-Code 승인, 교육과정과 기자재 구축, 교원역량 강화가 확인된다. 다만 졸업생 취업률과 장기 운영성과는 사업 종료 이후 추적이 필요하다.",
        "criteria-relevance": _criterion_body(by_id.get("relevance")),
        "criteria-coherence": _criterion_body(by_id.get("coherence")),
        "criteria-effectiveness": _criterion_body(by_id.get("effectiveness")),
        "criteria-efficiency": _criterion_body(by_id.get("efficiency")),
        "criteria-sustainability": _criterion_body(by_id.get("sustainability")),
        "criteria-crosscutting": next((q["finding"] for q in all_questions if q["question_id"] == "effectiveness-q3"), "성별·취약계층별 분리통계와 포용성 증빙을 추가 확보할 필요가 있다."),
        "criteria-other": "본 사업의 특수성으로는 현지 최초 응급구조학과의 제도화와 고등교육·응급의료 체계의 연계가 있다. 별도 점수 기준은 적용하지 않으며, 확산 가능성과 제도 정착 여부를 후속 추적 대상으로 관리한다.",
        "conclusion": f"{project}은 학과 개설과 제도 승인, 교육과정·교원·실습 인프라 구축 등 핵심 산출물을 전반적으로 달성하였다. 종합평가 결과는 {scored_total:.1f}/20으로 {government_grade} 수준이다. 다만 첫 졸업생 배출 이후 취업성과, 현지 재정과 운영 자립성, 포용성 분리통계가 충분히 확보되지 않아 중장기 성과는 후속 검증이 필요하다.",
        "working-factors": "주요 작동요인은 다음과 같다.\n- " + "\n- ".join(positives[:10] or ["수원국 관계기관의 제도 승인과 수행기관 간 협력"]),
        "nonworking-factors": "주요 비작동·제약 요인은 다음과 같다.\n- " + "\n- ".join(negatives[:10] or [gaps]),
        "theory": f"사업은 교육과정 개발, 교원역량 강화, 기자재 구축과 제도 승인을 통해 응급구조학과 운영 기반을 만들고, 양성된 인력이 응급의료 서비스 개선에 기여한다는 성과경로를 전제로 한다. 현재 {outputs}이 확인되어 산출 단계까지의 경로는 대체로 작동하였다. 반면 졸업생 취업과 장기 현장성과가 아직 확인되지 않아 성과에서 영향으로 이어지는 경로는 후속 추적이 필요하다.",
        "feedback": "환류과제\n" + "\n".join(f"{i}. 제언: {item}\n   이해관계자: 수행기관·수원기관·관계부처\n   선정 사유: 평가자료 공백 및 지속가능성 보완\n   후속 확인자료: 이행계획과 실적자료" for i, item in enumerate(actions[:8], 1)),
        "lessons": "교훈\n" + "\n".join(f"교훈 {i}. {item}\n교훈 내용: 유사 사업의 설계와 수행 단계에서 해당 조건을 사전에 점검하고 이행실적을 축적해야 한다.\n분야/일반 구분: 분야\n이전년도 교훈 중복 여부: 신규\n체크리스트 질문: 해당 조치의 책임주체·기한·검증자료가 사전에 정해졌는가?" for i, item in enumerate(actions[:6], 1)),
    }
    return {key: sanitize_report_text(value) for key, value in content.items()}


def validate_report_section_contracts() -> None:
    """Fail startup if any of the three 27-section contracts drift apart."""
    validate_hwpx_pipeline_contracts()
    prompt_ids = [str(item.get("id") or "") for item in EDITOR_REPORT_PARTS]
    pipeline_ids = [item.part_id for item in SECTION_PIPELINES]
    reference_ids = set(EDITOR_PART_REFERENCE_PIPELINES)
    if len(prompt_ids) != 27 or len(set(prompt_ids)) != 27:
        raise RuntimeError("보고서 전용 프롬프트는 중복 없이 정확히 27개여야 합니다.")
    if prompt_ids != pipeline_ids:
        raise RuntimeError("보고서 프롬프트 순서와 HWPX 섹션 순서가 일치하지 않습니다.")
    if set(prompt_ids) != reference_ids:
        raise RuntimeError("보고서 프롬프트와 문서 참고자료 계약의 섹션 ID가 일치하지 않습니다.")


def sync_report_sections(force_bootstrap: bool = False) -> None:
    validate_report_section_contracts()
    contents = bootstrap_contents()
    with connection() as conn, conn.transaction():
        for number, part in enumerate(EDITOR_REPORT_PARTS, 1):
            part_id = str(part["id"])
            row = conn.execute("SELECT content,status FROM report_sections WHERE part_id=%s", (part_id,)).fetchone()
            initial = contents.get(part_id, "")
            if row:
                existing_content = str(row.get("content") or "")
                normalized_content = canonical_narrative_outline_text(part_id, existing_content)
                next_content = initial if force_bootstrap else normalized_content
                content_changed = next_content != existing_content
                conn.execute(
                    """UPDATE report_sections SET section_number=%s,section_id=%s,title=%s,prompt=%s,
                       required_inputs=%s,updated_at=CASE WHEN %s OR %s THEN now() ELSE updated_at END,
                       content=%s,
                       status=CASE WHEN %s THEN 'draft' ELSE status END WHERE part_id=%s""",
                    (number, part.get("sectionId", part_id), part["title"], part["prompt"],
                     Jsonb(part.get("requiredInputs", [])), force_bootstrap, content_changed, next_content,
                     force_bootstrap, part_id),
                )
            else:
                conn.execute(
                    """INSERT INTO report_sections
                       (part_id,section_number,section_id,title,prompt,required_inputs,content,status,source_document_ids,generation_model,generated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'[]'::jsonb,%s,CASE WHEN %s THEN now() ELSE NULL END)""",
                    (part_id, number, part.get("sectionId", part_id), part["title"], part["prompt"],
                     Jsonb(part.get("requiredInputs", [])), initial, "draft" if initial else "empty",
                     "local-current-analysis" if initial else None, bool(initial)),
                )


def section_reference_route(part_id: str) -> dict:
    """Resolve the exact document contract for one report section."""
    pipeline = EDITOR_PART_REFERENCE_PIPELINES.get(part_id, {})
    criteria = list(dict.fromkeys(str(item) for item in pipeline.get("criteria", []) if str(item)))
    evidence = pipeline.get("evidence", {}) if isinstance(pipeline.get("evidence"), dict) else {}
    slot_titles = list(dict.fromkeys(
        str(title)
        for criterion in criteria
        for title in evidence.get(criterion, [])
        if str(title)
    ))
    return {
        "part_id": part_id,
        "criteria": criteria,
        "slot_titles": slot_titles,
        "notes": list(pipeline.get("notes", [])),
        "uses_uploaded_documents": bool(criteria or slot_titles),
    }


def section_documents(part_id: str, include_paths: bool = False) -> list[dict]:
    route = section_reference_route(part_id)
    criteria = route["criteria"]
    slot_titles = route["slot_titles"]
    # The TOC and notice are template-owned sections.  Passing every uploaded
    # document when their criteria list was empty made their evidence context
    # indistinguishable from other sections.
    if not route["uses_uploaded_documents"]:
        return []
    with connection() as conn:
        authoritative_pdm = conn.execute(
            """SELECT d.id,d.original_name,d.size_bytes,d.summary,d.analysis,d.extracted_path,
                      1.0::numeric AS confidence,
                      '가장 최근에 승인·구조화된 PDM 모델의 원문'::text AS rationale,
                      'authoritative-pdm'::text AS matched_via,
                      'relevance'::text AS matched_criterion,
                      NULL::text AS matched_slot_id,
                      '집행계획서 및 최신 PDM (Project Design Matrix)'::text AS matched_slot_title
                 FROM pdm_models p
                 JOIN intake_documents d ON d.id=p.source_document_id
                WHERE d.status='completed'
                ORDER BY
                  CASE
                    WHEN p.source_file_name ILIKE '%%최신%%PDM%%'
                      OR p.source_file_name ILIKE '%%PDM%%최신%%' THEN 0
                    WHEN p.source_file_name ILIKE '%%수정%%' THEN 1
                    ELSE 2
                  END,
                  p.created_at DESC
                LIMIT 1"""
        ).fetchone()
        if part_id == "pdm" and authoritative_pdm:
            rows = [authoritative_pdm]
        else:
            rows = conn.execute(
                """WITH ranked AS (
                     SELECT DISTINCT ON (d.id) d.id,d.original_name,d.size_bytes,d.summary,d.analysis,d.extracted_path,
                            COALESCE(s.confidence,a.confidence,0.5) AS confidence,
                            COALESCE(s.rationale,a.rationale,'섹션 전용 근거자료') AS rationale,
                            CASE WHEN s.id IS NOT NULL THEN 'section-suggestion' ELSE 'evidence-slot' END AS matched_via,
                            COALESCE(s.dac_criterion,a.criterion) AS matched_criterion,
                            a.slot_id AS matched_slot_id,a.slot_title AS matched_slot_title
                     FROM intake_documents d
                     LEFT JOIN slot_suggestions s ON s.document_id=d.id AND s.section_id=%s
                     LEFT JOIN document_slot_assignments a ON a.document_id=d.id
                           AND a.criterion=ANY(%s::text[]) AND a.slot_title=ANY(%s::text[])
                     WHERE d.status='completed' AND (s.id IS NOT NULL OR a.id IS NOT NULL)
                     ORDER BY d.id,COALESCE(s.confidence,a.confidence,0.5) DESC
                   )
                   SELECT * FROM ranked ORDER BY confidence DESC,original_name LIMIT 30""",
                (part_id, criteria, slot_titles),
            ).fetchall()
            if part_id == "achievement" and authoritative_pdm:
                authoritative_id = authoritative_pdm["id"]
                rows = [authoritative_pdm, *(row for row in rows if row["id"] != authoritative_id)]
    rows = [
        row for row in rows
        if is_report_evidence_document(row.get("original_name"), row.get("analysis"))
    ]
    authoritative_id = str(authoritative_pdm["id"]) if authoritative_pdm else ""
    items = [{
        **row,
        "id": str(row["id"]),
        "confidence": float(row["confidence"]),
        "is_authoritative_pdm": str(row["id"]) == authoritative_id,
    } for row in rows]
    items.sort(key=lambda item: (not item["is_authoritative_pdm"], -item["confidence"], item["original_name"]))
    if not include_paths:
        for item in items:
            item.pop("extracted_path", None)
    return items
