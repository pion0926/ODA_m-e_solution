from __future__ import annotations

import json
import re
import uuid

import httpx
from psycopg.types.json import Jsonb

from .assessment_context import assessment_scope
from .db import connection, open_pool, tenant_context
from .evaluation_criteria import COMMON_LEVELS, EVALUATION_CRITERIA
from .llm_models import current_llm_model, llm_model_context
from .project_overview import generate_project_overview
from .settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_REFERER
from .report_text import sanitize_report_text, sanitize_text_list
from .usage import record_token_usage
from .project_lifecycle import capture_input_snapshot
from .dac_evidence import prepare_documents
from .dac_pdm import refresh_context as refresh_pdm_context, attach_question_context
from .dac_scoring import scoring_definition, validate_scoring_trace

def _extract_json(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("평가 LLM 응답에서 JSON 객체를 찾지 못했습니다.")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise RuntimeError("평가 LLM 응답이 JSON 객체가 아닙니다.")
    return parsed


def _load_documents() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT d.*,COALESCE(array_agg(DISTINCT a.criterion)
                       FILTER (WHERE a.criterion IS NOT NULL),'{}') AS assigned_criteria
               FROM intake_documents d
               LEFT JOIN document_slot_assignments a ON a.document_id=d.id
               WHERE d.status='completed'
               GROUP BY d.id ORDER BY d.queue_position"""
        ).fetchall()
    documents = []
    for index, row in enumerate(rows, 1):
        analysis = row.get("analysis") or {}
        documents.append({
            "ref": f"D{index:03d}",
            "id": str(row["id"]),
            "name": row["original_name"],
            "summary": row.get("summary") or analysis.get("summary") or "",
            "document_type": analysis.get("document_type", ""),
            "period": analysis.get("period", ""),
            "organizations": analysis.get("organizations", []),
            "quality_flags": analysis.get("quality_flags", []),
            "assigned_criteria": sorted(set(row.get("assigned_criteria") or []) | set(analysis.get("dac_criteria") or [])),
            "extracted_path": row.get("extracted_path"),
            "stored_path": row.get("stored_path"),
            "sha256": str(row.get("sha256") or ""),
            "extension": row.get("extension"),
            "dac_fulltext_cache": analysis.get("dac_fulltext"),
        })
    return documents


def _corpus(criterion_id: str, documents: list[dict]) -> tuple[list[dict], dict[str, str]]:
    id_by_ref = {}
    corpus = []
    for doc in documents:
        relevant = criterion_id in doc["assigned_criteria"]
        review = doc.get("fulltext_review") or {}
        if relevant and review.get("status") != "completed":
            raise RuntimeError(f"DAC 전체 본문 분석이 완료되지 않았습니다: {doc['name']}")
        evidence = []
        for chunk in review.get("chunks", []):
            for item in chunk["evidence"]:
                if item["question_id"].startswith(criterion_id + "-") and item not in evidence:
                    evidence.append(item)
        if relevant and evidence:
            id_by_ref[doc["ref"]] = doc["id"]
        corpus.append({
            "ref": doc["ref"],
            "file_name": doc["name"],
            "relevant_slot_assignment": relevant,
            "document_type": doc["document_type"],
            "period": doc["period"],
            "organizations": doc["organizations"],
            "summary": doc["summary"] if not relevant else "전체 본문 분석 근거를 참조",
            "quality_flags": doc["quality_flags"],
            "fulltext_review": {"status": review.get("status"), "character_count": review.get("character_count", 0),
                                "chunk_count": len(review.get("chunks", []))},
            "question_evidence": evidence,
        })
    return corpus, id_by_ref


def _call(criterion_id: str, criterion: dict, corpus: list[dict], assessment: dict, pdm_context: dict | None = None, validation_feedback: str = "") -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY가 설정되지 않았습니다.")
    response_template = {
        "summary": "기준 전체 종합 판단 3~5문장", "score_reason": "질문별 점수 평균의 핵심 산정 이유",
        "question_assessments": [{
            "question_id": question["id"], "score": 1,
            "scoring_trace": {
                "selected_level_reason": "선택 점수 요건과 실제 확인 사실의 구체적 대조",
                "next_level_gap": "바로 위 점수에 부족한 근거 또는 4점 유지 과제",
                "checks": [{"check_id": check["id"], "status": "unverified",
                            "finding": "이 확인 항목에 관한 구체적인 근거 설명 및 한계",
                            "evidence_document_refs": []} for check in scoring_definition(question)["checks"]],
            },
            "finding": "질문 전체의 근거 중심 판단", "positive_evidence": [], "limitations": [],
            "evidence_document_refs": [], "pdm_indicator_ids": [], "evidence_gaps": [], "action_items": [],
        } for question in criterion["questions"]],
    }
    prompt = f"""당신은 ODA 사업의 독립 평가전문가다.
검증된 평가질문과 1~4점 루브릭을 일관되게 적용한다.
제공된 {len(corpus)}개 문서 중 relevant_slot_assignment=true인 모든 문서는 본문 전체를 구간별로 검토했다.
question_evidence는 전체 본문 검토에서 수집한 원문 인용과 질문별 근거다. 모든 근거를 함께 검토하여 질문별 점수를 판단한다.
연결되지 않은 문서의 요약은 자료 목록의 배경 정보일 뿐 점수·수치·판단의 증빙으로 사용하지 않는다.
긍정·반대 근거를 모두 고려하고 문서 간 기간·대상·수치 차이와 충돌을 명시한다. 중복 문서를 중복 성과로 계산하지 않는다.
최신 PDM 평가 정보의 논리구조, 모든 지표의 목표·실적·달성도, 검증수단, 가정, 증빙 연결, 확인 필요 사항과 위험 분석을 모두 검토한다.
PDM 수치와 그 출처를 문서 근거와 대조한다. 특히 효과성에서는 산출물과 성과 지표를 구분하여 판단한다.
과거 문서의 실적 공란만으로 현재 확인된 PDM 실적을 없다고 단정하지 않는다. 측정기간 미상이나 자료 충돌은 명시한다.
PDM의 실적 미확인·분석 미완료는 0%가 아니며, 합격률 같은 실적 비율과 목표 대비 달성도를 구분한다.
PDM 달성도를 DAC 1~4점으로 기계적으로 변환하지 않는다. 점수는 해당 질문의 루브릭으로 판단한다.
PDM 위험 분석은 파생된 해석이므로 확정 사실로 재인용하지 말고 원문·수치로 검증한다.
각 질문에서 사용한 PDM 지표 id를 pdm_indicator_ids에 명시하고, 관련성이 없으면 빈 배열로 둔다.
문서에 없는 사실을 만들지 않는다. 자료 부재만으로 자동 감점하지 말고 확인된 성과와 한계를 함께 판단한다.
문서 참조번호(D001 형식)는 evidence_document_refs 배열에만 넣는다. summary, score_reason,
finding, positive_evidence, limitations, evidence_gaps, action_items에는 D001 같은 내부번호를 절대 쓰지 않는다.
점수는 각 질문별 정수 1~4점이다.
각 질문의 내부 확인 항목을 모두 검토하고 충족(met), 일부 충족(partial), 미충족(not_met), 미확인(unverified)을 구분한다.
자료 없음은 실패 증명이 아니므로 unverified로 기록한다. 해당 항목을 거짓으로 met/not_met 처리하지 않는다.
각 항목의 finding에는 무엇을 어느 시점의 어떤 자료로 확인했고 무엇이 부족한지 작성한다.
점수는 체크 수의 기계적 합산이 아니라 질문별 1~4점 요건에 대조하여 선정한다.
selected_level_reason은 선택 점수 요건과 실제 확인 내용을 연결하고, next_level_gap은 바로 위 점수 요건 중 부족하거나 미확인인 점을 명시한다.
4점은 모든 확인 항목 충족과 해당 질문 4점의 추가 성과·자립 등 특수 요건까지 증명해야 한다. 4점의 next_level_gap에는 추가 유지·검증 과제를 쓴다.
일부 자료가 미확인이면 확인된 범위로 잠정 판단하고 불확실성을 이유에 명시한다. 내부 기준을 OECD 공식 점수표라고 표현하지 않는다.
project_status가 ongoing이면 이 작업을 종료평가라고 부르거나 사업이 완료되었다고 단정하지 않는다.

[내부 확인 항목 — 항목 ID 및 순서 준수]
{json.dumps([scoring_definition(q) for q in criterion['questions']], ensure_ascii=False)}

[이전 응답 검증 피드백 — 있을 경우 수정]
{validation_feedback}

[평가 시점과 사업 상태]
{json.dumps(assessment, ensure_ascii=False, indent=2)}

[평가기준]
{criterion['name']} ({criterion_id})

[공통 점수 의미]
{json.dumps(COMMON_LEVELS, ensure_ascii=False, indent=2)}

[질문과 루브릭]
{json.dumps(criterion['questions'], ensure_ascii=False, indent=2)}

[전체 문서 코퍼스]
{json.dumps(corpus, ensure_ascii=False)}

[최신 PDM 평가 정보 — 이번 평가에 고정한 스냅샷]
{json.dumps(pdm_context or {'status': 'unavailable'}, ensure_ascii=False)}

[반환 JSON]
{{
  "summary":"기준 전체 종합 판단 3~5문장",
  "score_reason":"질문별 점수 평균의 핵심 산정 이유",
  "question_assessments":[
    {{
      "question_id":"정의된 질문 id",
      "score":1,
      "scoring_trace": {{"selected_level_reason":"선택한 점수의 요건과 확인된 사실을 대조한 이유", "next_level_gap":"상위 점수의 미충족·미확인 요건과 필요한 근거", "checks":[{{"check_id":"정의된 확인 항목 id", "status":"met/partial/not_met/unverified 중 하나", "finding":"해당 항목의 구체적 확인 결과와 한계", "evidence_document_refs":["D001"]}}]}},
      "finding":"루브릭과 문서 근거에 따른 구체적 판단 3~6문장",
      "positive_evidence":["확인된 긍정 근거"],
      "limitations":["확인된 한계 또는 반대 근거"],
      "evidence_document_refs":["D001"],
      "pdm_indicator_ids":["관련 PDM 지표 id, 관련 없으면 빈 배열"],
      "evidence_gaps":["점수 확정성과 보고서 품질을 위해 부족한 증빙"],
      "action_items":["구체적 보완 조치"]
    }}
  ]
}}
질문 수와 순서는 정의와 정확히 같아야 한다. JSON 객체만 반환한다."""
    prompt += f"""\n[완전한 반환 구조: 아래 모든 질문·확인 ID를 빠짐없이 유지]
앞의 축약 예시가 아니라 이 전체 구조의 각 설명·점수·상태·참조를 실제 판단으로 바꾸어 반환한다.
score=1과 status=unverified는 예시 기본값일 뿐 판단을 유도하지 않는다. 실제 근거와 1~4점 요건에 따라 정한다.
각 질문 checks는 정확히 3개이다. 첫 항목만 반환하거나 서로 합치지 않는다.
{json.dumps(response_template, ensure_ascii=False)}"""
    payload = {
        "model": current_llm_model(),
        "messages": [
            {"role": "system", "content": "근거 중심의 보수적 ODA 평가를 수행하고 유효한 JSON만 반환한다."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": "KODAME Criterion Evaluation",
    }
    with httpx.Client(timeout=httpx.Timeout(360.0, connect=30.0)) as client:
        response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter 평가 호출 실패: HTTP {response.status_code} {response.text[:300]}")
    try:
        body = response.json()
        record_token_usage(body, payload["model"])
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("OpenRouter 평가 응답 구조를 해석할 수 없습니다.") from exc
    return _extract_json(content)


def _phase_safe_text(value: object, assessment: dict) -> str:
    text = sanitize_report_text(value)
    text = re.sub(
        r"(?i)(?<![0-9a-z])[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![0-9a-z])",
        "",
        text,
    )
    if assessment.get("project_status") == "ongoing":
        text = re.sub(r"종료\s*평가", "현재시점 평가", text)
        text = re.sub(r"본\s*사업(?:은|이)?\s*완료되었", "현재까지 확인된 사업활동은 수행되었", text)
    return text


def _phase_safe_list(value: object, assessment: dict, max_length: int) -> list[str]:
    return [_phase_safe_text(item, assessment)[:max_length] for item in sanitize_text_list(value, max_length)]


def _validate(criterion: dict, result: dict, id_by_ref: dict[str, str], assessment: dict) -> dict:
    raw = result.get("question_assessments")
    if not isinstance(raw, list) or len(raw) != len(criterion["questions"]):
        raise RuntimeError("평가 질문 수가 정의와 일치하지 않습니다.")
    assessments = []
    all_evidence: list[str] = []
    all_gaps: list[str] = []
    for definition, item in zip(criterion["questions"], raw):
        trace = validate_scoring_trace(definition, item, id_by_ref)
        score = trace["selected_score"]
        refs = list(dict.fromkeys([
            *[ref for ref in item.get("evidence_document_refs", []) if ref in id_by_ref],
            *[ref for check in trace["checks"] for ref in check["evidence_document_refs"]],
        ]))
        evidence_ids = list(dict.fromkeys(id_by_ref[ref] for ref in refs))
        gaps = _phase_safe_list(item.get("evidence_gaps", []), assessment, 500)
        all_evidence.extend(evidence_ids)
        all_gaps.extend(gaps)
        assessments.append({
            "question_id": definition["id"],
            "question": definition["question"],
            "score": score,
            "scoring_trace": trace,
            "finding": _phase_safe_text(item.get("finding", ""), assessment)[:5000],
            "positive_evidence": _phase_safe_list(item.get("positive_evidence", []), assessment, 1000),
            "limitations": _phase_safe_list(item.get("limitations", []), assessment, 1000),
            "evidence_document_ids": evidence_ids,
            "evidence_document_refs": refs,
            "pdm_indicator_ids": item.get("pdm_indicator_ids", []),
            "evidence_gaps": gaps,
            "action_items": _phase_safe_list(item.get("action_items", []), assessment, 1000),
            "levels": definition["levels"],
        })
    score = round(sum(item["score"] for item in assessments) / len(assessments), 1)
    return {
        "score": score,
        "summary": _phase_safe_text(result.get("summary", ""), assessment)[:10000],
        "score_reason": _phase_safe_text(result.get("score_reason", ""), assessment)[:5000],
        "question_assessments": assessments,
        "evidence_document_ids": list(dict.fromkeys(all_evidence)),
        "evidence_gaps": list(dict.fromkeys(all_gaps)),
    }


def run_all(
    run_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    model: str | None = None,
) -> uuid.UUID:
    with tenant_context(project_id, system=project_id is None), llm_model_context(model):
        return _run_all(run_id)


def _run_all(run_id: uuid.UUID | None = None) -> uuid.UUID:
    open_pool()
    selected_model = current_llm_model()
    input_snapshot = capture_input_snapshot()
    documents = _load_documents()
    queued_run_id = run_id
    run_id = run_id or uuid.uuid4()
    with connection() as conn, conn.transaction():
        if queued_run_id:
            conn.execute(
                """UPDATE evaluation_runs
                   SET status='running',model=%s,document_count=%s,started_at=now(),completed_at=NULL,error_message=NULL,input_snapshot=%s
                   WHERE id=%s""",
                (selected_model, len(documents), Jsonb(input_snapshot), run_id),
            )
        else:
            conn.execute(
                "INSERT INTO evaluation_runs(id,status,model,document_count,input_snapshot) VALUES (%s,'running',%s,%s,%s)",
                (run_id, selected_model, len(documents), Jsonb(input_snapshot)),
            )
    try:
        print(f"GENERATING PROJECT OVERVIEW with {len(documents)} documents", flush=True)
        generate_project_overview(run_id)
        print("COMPLETED PROJECT OVERVIEW", flush=True)
        with connection() as conn:
            overview_row = conn.execute(
                "SELECT overview FROM project_overviews WHERE run_id=%s ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        assessment = assessment_scope(overview_row["overview"] if overview_row else {})
        pdm_context = refresh_pdm_context(documents)
        with connection() as conn:
            conn.execute("UPDATE evaluation_runs SET input_snapshot=jsonb_set(input_snapshot,'{pdm_context}',%s) WHERE id=%s",
                         (Jsonb(pdm_context), run_id))
        prepare_documents(documents)
        for criterion_id, criterion in EVALUATION_CRITERIA.items():
            print(f"EVALUATING {criterion_id} with {len(documents)} documents", flush=True)
            corpus, id_by_ref = _corpus(criterion_id, documents)
            id_by_ref.update(pdm_context.get("evidence_document_refs", {}))
            feedback = ""
            for attempt in range(3):
                raw = _call(criterion_id, criterion, corpus, assessment, pdm_context, feedback)
                try:
                    result = _validate(criterion, raw, id_by_ref, assessment)
                    break
                except (ValueError, RuntimeError, TypeError) as exc:
                    print(f"DAC_RUBRIC_VALIDATION {criterion_id} attempt={attempt + 1}: {exc}", flush=True)
                    if attempt == 2:
                        raise
                    feedback = str(exc)
            for question in result["question_assessments"]:
                question["evidence_quotes"] = [
                    {"document_id": doc["id"], "file_name": doc["name"], **item}
                    for doc, source in zip(documents, corpus)
                    if doc["id"] in question["evidence_document_ids"]
                    for item in source["question_evidence"]
                    if item["question_id"] == question["question_id"]
                ]
                question["document_review"] = {
                    "method": "fulltext_chunks",
                    "document_count": sum(source["relevant_slot_assignment"] for source in corpus),
                    "chunk_count": sum(source["fulltext_review"]["chunk_count"] for source in corpus if source["relevant_slot_assignment"]),
                }
                attach_question_context(question, pdm_context)
            result["evidence_document_ids"] = list(dict.fromkeys(
                doc_id for question in result["question_assessments"] for doc_id in question["evidence_document_ids"]
            ))
            with connection() as conn, conn.transaction():
                conn.execute(
                    """INSERT INTO criterion_evaluations
                       (run_id,criterion_id,criterion_name,score,summary,score_reason,
                        question_assessments,evidence_document_ids,evidence_gaps,source_document_count)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (run_id, criterion_id, criterion["name"], result["score"], result["summary"],
                     result["score_reason"], Jsonb(result["question_assessments"]),
                     Jsonb(result["evidence_document_ids"]), Jsonb(result["evidence_gaps"]), len(documents)),
                )
            print(f"COMPLETED {criterion_id} score={result['score']}", flush=True)
        with connection() as conn, conn.transaction():
            conn.execute("UPDATE evaluation_runs SET status='completed',completed_at=now() WHERE id=%s", (run_id,))
    except Exception as exc:
        with connection() as conn, conn.transaction():
            conn.execute(
                "UPDATE evaluation_runs SET status='failed',error_message=%s,completed_at=now() WHERE id=%s",
                (str(exc)[:4000], run_id),
            )
        raise
    print(f"EVALUATION_RUN_COMPLETE {run_id}", flush=True)
    return run_id


if __name__ == "__main__":
    run_all()
