from __future__ import annotations

import json
import re
import uuid

import httpx
from psycopg.types.json import Jsonb

from .db import connection
from .llm_models import current_llm_model
from .openrouter import redact_for_external_analysis
from .report_sources import is_report_evidence_document, reader_source_label
from .settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_REFERER
from .usage import record_token_usage


FIELDS = (
    "project_name", "country", "location", "period", "budget", "donor",
    "implementer", "partner", "background", "objective", "beneficiaries",
    "activities", "outputs", "outcomes", "stakeholders", "timeline", "evidence_gaps",
)


def _extract_json(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("사업개요 응답에서 JSON 객체를 찾지 못했습니다.")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise RuntimeError("사업개요 응답이 JSON 객체가 아닙니다.")
    return parsed


def _documents() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT id,original_name,summary,analysis,queue_position
               FROM intake_documents WHERE status='completed' ORDER BY queue_position"""
        ).fetchall()
    rows = [row for row in rows if is_report_evidence_document(row["original_name"], row.get("analysis"))]
    authoritative = [
        row for row in rows
        if "사업계획서" in row["original_name"]
        or ("PDM" in row["original_name"].upper() and row["original_name"].lower().endswith(".pdf"))
    ]
    rows = authoritative or rows
    result = []
    for index, row in enumerate(rows, 1):
        analysis = row.get("analysis") or {}
        result.append({
            "ref": f"D{index:03d}", "id": str(row["id"]),
            "name": reader_source_label(row["original_name"], analysis),
            "title": analysis.get("title", ""), "type": analysis.get("document_type", ""),
            "period": analysis.get("period", ""), "organizations": analysis.get("organizations", []),
            "summary": row.get("summary") or analysis.get("summary", ""),
            "quality_flags": analysis.get("quality_flags", []),
        })
    return result


def overview_source_document_count() -> int:
    """Return the evidence count used by the overview generator for this project."""
    return len(_documents())


def _normalize_item(value) -> dict:
    if isinstance(value, dict):
        text = str(value.get("text") or value.get("value") or "").strip()[:12000]
        refs = [str(ref) for ref in value.get("source_refs", []) if re.fullmatch(r"D\d{3}", str(ref))]
        return {"text": text, "source_refs": list(dict.fromkeys(refs))}
    return {"text": str(value or "").strip()[:12000], "source_refs": []}


def generate_project_overview(run_id: uuid.UUID | None = None) -> uuid.UUID:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY가 설정되지 않았습니다.")
    documents = _documents()
    if not documents:
        raise RuntimeError("사업개요를 생성할 완료 문서가 없습니다.")
    corpus = "\n".join(
        f"[{d['ref']}] 파일: {d['name']} | 문서명: {d['title']} | 유형: {d['type']} | "
        f"기간: {d['period']} | 기관: {', '.join(d['organizations'])} | 요약: {d['summary']} | "
        f"주의: {', '.join(d['quality_flags'])}"
        for d in documents
    )
    corpus, _ = redact_for_external_analysis(corpus)
    prompt = f"""아래 {len(documents)}개 사업계획서와 PDM 문서 요약을 교차 검토하여 최신 사업개요를 작성하라.
사업 기본정보는 사업계획서를 우선하고, 목표·활동·산출·성과의 논리구조는 가장 최신 PDM을 우선한다.
문서에 명시된 사실만 사용하고, 각 항목은 반드시 근거 문서 번호를 source_refs에 기록한다.
수치·기간·기관명이 충돌하면 임의로 하나를 확정하지 말고 conflicts에 양쪽 값과 근거를 기록한다.
정보가 없으면 text를 '확인 필요'로 하고 evidence_gaps에도 기록한다.

반환 JSON 형식:
{{
  "project_name": {{"text":"", "source_refs":["D001"]}},
  "country": {{"text":"", "source_refs":[]}},
  "location": {{"text":"", "source_refs":[]}},
  "period": {{"text":"", "source_refs":[]}},
  "budget": {{"text":"", "source_refs":[]}},
  "donor": {{"text":"", "source_refs":[]}},
  "implementer": {{"text":"", "source_refs":[]}},
  "partner": {{"text":"", "source_refs":[]}},
  "background": {{"text":"3~6문장", "source_refs":[]}},
  "objective": {{"text":"3~6문장", "source_refs":[]}},
  "beneficiaries": {{"text":"", "source_refs":[]}},
  "activities": {{"text":"주요 활동을 줄바꿈 목록으로", "source_refs":[]}},
  "outputs": {{"text":"확인된 산출물", "source_refs":[]}},
  "outcomes": {{"text":"확인된 또는 예상 성과", "source_refs":[]}},
  "stakeholders": {{"text":"기관별 역할", "source_refs":[]}},
  "timeline": {{"text":"연차별 주요 경과", "source_refs":[]}},
  "evidence_gaps": {{"text":"미확보·추가 확인 정보", "source_refs":[]}},
  "conflicts": [{{"field":"budget", "description":"충돌 설명", "values":[{{"value":"", "source_refs":[]}}]}}]
}}

[문서 목록]
{corpus}"""
    selected_model = current_llm_model()
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": "당신은 ODA 사업개요 작성 전문가다. 근거 없는 추론을 금지하며 JSON 객체만 반환한다."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER, "X-Title": "KODAME Project Overview",
    }
    with httpx.Client(timeout=httpx.Timeout(240.0, connect=20.0)) as client:
        response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"사업개요 OpenRouter 호출 실패: HTTP {response.status_code}")
    try:
        body = response.json()
        record_token_usage(body, payload["model"])
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("사업개요 OpenRouter 응답 구조를 해석할 수 없습니다.") from exc
    parsed = _extract_json(raw)
    overview = {field: _normalize_item(parsed.get(field)) for field in FIELDS}
    valid_refs = {d["ref"] for d in documents}
    for item in overview.values():
        item["source_refs"] = [ref for ref in item["source_refs"] if ref in valid_refs]
    conflicts = parsed.get("conflicts", []) if isinstance(parsed.get("conflicts"), list) else []
    overview_id = uuid.uuid4()
    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO project_overviews
               (id,run_id,model,document_count,overview,source_document_ids,conflicts)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (overview_id, run_id, selected_model, len(documents), Jsonb(overview),
             Jsonb([d["id"] for d in documents]), Jsonb(conflicts[:50])),
        )
    return overview_id


def generate_local_bootstrap_overview() -> uuid.UUID:
    """Deprecated: historical sample-data seeding is forbidden in service mode.

    The clone/recovery CLIs must use the normal evidence-backed evaluation flow.
    Retain an explicit exception rather than silently treating one demonstration
    project's hard-coded facts as a newly provisioned customer's facts.
    """
    raise RuntimeError("고정 샘플 사업개요 생성은 비활성화되었습니다. 현재 프로젝트 자료로 전체 문서 재평가를 실행해 주세요.")

