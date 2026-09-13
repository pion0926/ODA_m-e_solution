from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .llm_models import current_llm_model
from .settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_REFERER
from .taxonomy import DAC_CRITERIA, SECTION_BY_ID, prompt_taxonomy
from .usage import record_token_usage
from .performance_risk_policy import RISK_SYSTEM_PROMPT, validate_risk_result

class MissingApiKey(RuntimeError):
    pass

class AnalysisError(RuntimeError):
    pass

SYSTEM_PROMPT = """당신은 KOICA/ODA 종료평가 문서 분류 전문가다. 제공된 문서에 명시된 사실만 사용한다.
문서 하나는 서로 다른 보고서 섹션 여러 곳에 근거가 될 수 있다. 제목이나 파일명만으로 분류하지 말고 본문 근거를 확인한다.
관련성이 약한 섹션은 넣지 않는다. confidence는 0~1이다. evidence_quote는 원문에서 짧게 발췌하고 없으면 빈 문자열이다.
반드시 JSON 객체 하나만 반환하며 Markdown 코드블록은 사용하지 않는다."""

SENSITIVE_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[이메일 비식별]"),
    (re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)"), "[전화번호 비식별]"),
    (re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)"), "[주민번호 비식별]"),
    (re.compile(r"(?<!\d)\d{2,6}[- ]\d{2,6}[- ]\d{2,8}(?!\d)"), "[식별번호 비식별]"),
]

def redact_for_external_analysis(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    redacted = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            flags.append(f"{replacement}:{count}")
    return redacted, flags

def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisError("LLM 응답이 유효한 JSON이 아닙니다.") from exc
    if not isinstance(value, dict):
        raise AnalysisError("LLM 응답 최상위 값이 객체가 아닙니다.")
    return value

def _request_json(system_prompt: str, user_prompt: str, title: str) -> tuple[dict, str]:
    if not OPENROUTER_API_KEY:
        raise MissingApiKey("OPENROUTER_API_KEY가 설정되지 않았습니다.")
    model = current_llm_model()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": title,
    }
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
        response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise AnalysisError(f"OpenRouter 호출 실패: HTTP {response.status_code}")
    try:
        body = response.json()
        record_token_usage(body, model)
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AnalysisError("OpenRouter 응답 구조를 해석할 수 없습니다.") from exc
    return _extract_json(content), model

def analyze_document(file_name: str, text: str) -> dict:
    excerpt, local_sensitive_flags = redact_for_external_analysis(text[:120000])
    user_prompt = f"""파일명: {file_name}

[ODA DAC 분류 기준]
{json.dumps(DAC_CRITERIA, ensure_ascii=False, indent=2)}

[보고서 27개 섹션 기준]
{prompt_taxonomy()}

[반환 형식]
{{
  "title": "공식 문서명",
  "document_type": "보고서/조사자료/회의록/행정자료/계획서/통계자료/계약·재무/정책·전략/기타 중 하나",
  "summary": "사실 중심 5문장 이내 요약",
  "language": "언어",
  "period": "대상기간 또는 빈 문자열",
  "organizations": ["생산·책임기관"],
  "oda_categories": ["사업기획", "성과관리"],
  "dac_criteria": ["relevance"],
  "confidentiality": "public/internal/personal/sensitive 중 하나",
  "quality_flags": ["결측이나 해석상 주의점"],
  "section_matches": [
    {{"section_id":"project-background","confidence":0.91,"rationale":"배정 이유","evidence_quote":"근거 문장","category":"수요·정책환경","dac_criterion":"relevance"}}
  ]
}}

[문서 본문]
{excerpt}"""
    result, _ = _request_json(SYSTEM_PROMPT, user_prompt, "KODAME Document Intake")
    result["local_sensitive_flags"] = local_sensitive_flags
    matches = []
    for item in result.get("section_matches", [])[:12]:
        section_id = str(item.get("section_id", ""))
        if section_id not in SECTION_BY_ID:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.45:
            continue
        number, _, title, _ = SECTION_BY_ID[section_id]
        matches.append({
            "section_id": section_id, "section_number": number, "section_title": title,
            "confidence": confidence, "rationale": str(item.get("rationale", ""))[:2000],
            "evidence_quote": str(item.get("evidence_quote", ""))[:1000],
            "category": str(item.get("category", "기타"))[:200],
            "dac_criterion": str(item.get("dac_criterion", ""))[:100] or None,
        })
    result["section_matches"] = matches
    return result

def clean_risk_text(value: object) -> str:
    """Normalize frequent punctuation/spacing damage in model-generated risk prose."""
    text = str(value or "").strip()
    text = re.sub(r"\bstatus\s*=\s*['\"]?unset['\"]?", "실적 미확인", text, flags=re.I)
    text = re.sub(r"협\s*,\s*공문", "협의 공문", text)
    text = re.sub(r"([가-힣])\s*,\s*([가-힣])", r"\1, \2", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"([,.;:])(?=[가-힣A-Za-z])", r"\1 ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text

def analyze_performance_risks(indicators: list[dict]) -> dict:
    candidates = [{
        "id": str(item.get("id", "")),
        "program": str(item.get("program", "")),
        "indicator": str(item.get("indicator", "")),
        "target": str(item.get("target", "")),
        "actual": str(item.get("actual", "")),
        "achievement_rate": item.get("achievement_rate"),
        "status": str(item.get("status", "")),
        "evidence": str(item.get("evidence", "")),
        "note": str(item.get("note", "")),
        "evidence_document_count": len(item.get("evidence_document_ids") or []),
    } for item in indicators if item.get("status") != "ok"]
    if not candidates:
        return {"items": [], "model": current_llm_model()}
    indicator_json, _ = redact_for_external_analysis(json.dumps(candidates[:40], ensure_ascii=False, indent=2))
    user_prompt = f"""[시스템 기준일: {datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()}]
권고 기한은 검토 착수 후 N일 이내처럼 상대기한만 사용한다.
[성과지표]
{indicator_json}

[반환 형식]
{{
  "items": [
    {{
      "id": "입력 id와 동일",
      "risk_title": "핵심 위험 제목",
      "risk_analysis": "목표·실적·달성도와 산출근거를 인용한 구체적 위험 분석",
      "root_causes": ["자료로 확인되는 원인 또는 확인이 필요한 원인"],
      "forecast": "조치하지 않을 경우의 합리적 전망",
      "recommendations": ["담당주체·기한·조치·확인자료가 드러나는 실행 권고"],
      "evidence_needed": ["추가 확보 또는 확인할 자료"],
      "priority": "high/medium/low 중 하나"
    }}
  ]
}}"""
    feedback = ""
    for attempt in range(3):
        result, model = _request_json(RISK_SYSTEM_PROMPT, user_prompt + feedback, "KODAME Performance Risk Analysis")
        try:
            validate_risk_result(result, candidates)
            break
        except ValueError as exc:
            if attempt == 2:
                raise AnalysisError(f"리스크 품질 검증 실패: {exc}") from exc
            feedback = f"\n[이전 응답 수정 요구]\n{exc}\n모든 입력 항목을 다시 완전한 JSON으로 작성한다."
    valid_ids = {item["id"] for item in candidates}
    normalized = []
    for item in result.get("items", [])[:len(candidates)]:
        indicator_id = str(item.get("id", ""))
        if indicator_id not in valid_ids:
            continue
        def string_list(key: str, limit: int) -> list[str]:
            values = item.get(key) if isinstance(item.get(key), list) else []
            return [clean_risk_text(value)[:1000] for value in values if clean_risk_text(value)][:limit]
        priority = str(item.get("priority", "medium")).lower()
        normalized.append({
            "id": indicator_id,
            "risk_title": clean_risk_text(item.get("risk_title"))[:500],
            "risk_analysis": clean_risk_text(item.get("risk_analysis"))[:4000],
            "root_causes": string_list("root_causes", 5),
            "forecast": clean_risk_text(item.get("forecast"))[:2000],
            "recommendations": string_list("recommendations", 6),
            "evidence_needed": string_list("evidence_needed", 6),
            "priority": priority if priority in {"high", "medium", "low"} else "medium",
            "analysis_source": "openrouter",
        })
    return {"items": normalized, "model": model}
