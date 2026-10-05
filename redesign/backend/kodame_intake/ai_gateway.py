from __future__ import annotations
from .ai.prompt_registry import load_prompt
from .model_catalog import prepare_model_payload
from .ai.provider_errors import error_info, is_context_limit, is_schema_rejection

import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .llm_models import current_llm_model
from .settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_REFERER
from .taxonomy import DAC_CRITERIA, SECTION_BY_ID, prompt_taxonomy
from .usage import record_token_usage
from .performance_risk_policy import RISK_SYSTEM_PROMPT, validate_risk_result
from .structured_output import OUTPUT_RULES, parse_object, validate_schema

class MissingApiKey(RuntimeError):
    pass

class AnalysisError(RuntimeError):
    pass

class OutputLimitError(AnalysisError):
    """Retry with a smaller input/output task, never the same oversized task."""

class ContextLimitError(AnalysisError):
    """The task needs less input, not different credentials."""

class ProviderTransientError(RuntimeError):
    """Transport retry budget exhausted; do not multiply retries by splitting text."""

class BillingError(RuntimeError):
    """A credit failure cannot be fixed by asking the model to reformat its response."""
    pass

class ConfigurationError(RuntimeError):
    """Provider request/configuration failures are not model-output format errors."""
    pass

class RefusalError(RuntimeError):
    """Do not retry provider refusals as formatting errors."""
    pass

SYSTEM_PROMPT = load_prompt("document_intake")

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
        if replacement == '[식별번호 비식별]':
            count = 0
            def replace_identifier(match):
                nonlocal count
                value = match.group()
                # Spaces also separate table cells. A bare numeric sequence is
                # not an identifier; require a nearby label in that case.
                # Dedicated phone and resident-ID rules above still apply.
                if '-' not in value:
                    prefix = redacted[max(0, match.start() - 80):match.start()]
                    if not re.search(
                        r'(?:계좌(?:번호)?|식별번호|사업자(?:등록)?번호|법인등록번호|'
                        r'여권번호|account(?:\s+(?:number|no\.?))?|passport(?:\s+(?:number|no\.?))?)'
                        r'[^\d\n]{0,30}$', prefix, re.IGNORECASE,
                    ):
                        return value
                if re.fullmatch(r'(?:19|20)\d{2}-\d{1,2}-\d{1,2}', value):
                    try:
                        datetime.strptime(value, '%Y-%m-%d')
                        return value
                    except ValueError:
                        pass
                count += 1
                return replacement
            redacted = pattern.sub(replace_identifier, redacted)
        else:
            redacted, count = pattern.subn(replacement, redacted)
        if count:
            flags.append(f"{replacement}:{count}")
    return redacted, flags

def _extract_json(text: str) -> dict:
    try:
        return parse_object(text)
    except (ValueError, TypeError) as exc:
        raise AnalysisError(f"LLM 응답이 유효한 JSON 객체가 아닙니다: {type(exc).__name__}") from exc

def _request_json(system_prompt: str, user_prompt: str, title: str, *, response_schema: dict | None = None,
                  output_tokens: int | None = None, temperature: float | None = None,
                  timeout: float = 180.0, few_shot_messages: list[dict] | None = None) -> tuple[dict, str]:
    from .intake_control import check
    check()
    if not OPENROUTER_API_KEY:
        raise MissingApiKey("OPENROUTER_API_KEY가 설정되지 않았습니다.")
    model = current_llm_model()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt + OUTPUT_RULES},
                     *(few_shot_messages or []), {"role": "user", "content": user_prompt}],
        "temperature": temperature if temperature is not None else (0 if 'DAC' in title else 0.1),
        "response_format": {"type": "json_object"},
    }
    if title == 'KODAME DAC Full Document Review':
        payload['max_tokens'] = 12000
    elif title == 'KODAME DAC Evidence Adjudication':
        payload['max_tokens'] = 12000
    elif title == 'KODAME Project Overview':
        payload['max_tokens'] = 16000
    if output_tokens is not None:
        payload['max_tokens'] = min(24000,max(1000,output_tokens))
    if response_schema is not None:
        payload['response_format'] = {'type':'json_schema','json_schema':{
            'name':'kodame_structured_result','strict':True,'schema':response_schema}}
        payload['provider'] = {'require_parameters':True}
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": title,
    }
    from .ai.request_limits import request_slot
    with httpx.Client(timeout=httpx.Timeout(min(timeout,420), connect=20.0)) as client:
        for attempt in range(3):
            try:
                check()
                with request_slot(payload) as reservation:
                    response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=prepare_model_payload(payload))
                    from .ai.global_budget import settle
                    try:
                        wire_usage = response.json()
                    except ValueError:
                        wire_usage = {}
                    settle(reservation, wire_usage)
                check()
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise ProviderTransientError('AI 공급자 연결이 반복 실패했습니다. 완료 결과는 보존됩니다.') from exc
                time.sleep(2 ** attempt)
                continue
            code, detail, metadata = error_info(response.status_code, wire_usage)
            choices = wire_usage.get('choices') or [] if isinstance(wire_usage, dict) else []
            finish_error = bool(isinstance(choices, list) and choices and isinstance(choices[0], dict)
                                and choices[0].get('finish_reason') == 'error')
            if code in (408, 429, 500, 502, 503, 504) or (code < 400 and finish_error):
                if attempt < 2:
                    try:
                        delay = float(response.headers.get('Retry-After', 2 ** attempt))
                    except ValueError:
                        delay = 2 ** attempt
                    time.sleep(min(30, max(1, delay)))
                    continue
                raise ProviderTransientError(f'AI 공급자 오류가 반복되었습니다: {code} · {detail}')
            # A provider may offer JSON mode without native strict schemas. Only
            # downgrade the wire format for an explicit capability rejection;
            # the selected model and local validation remain unchanged.
            if response_schema and payload['response_format']['type'] == 'json_schema' and code in (400, 404):
                if is_schema_rejection(detail) and attempt < 2:
                    payload['response_format'] = {'type': 'json_object'}
                    payload['messages'][0]['content'] += '\nJSON Schema (validate every field):\n' + json.dumps(response_schema, ensure_ascii=False)
                    continue
            if code != 402:
                break
            if metadata.get('limit_source') == 'openrouter_in_flight_budget' and attempt < 2:
                try:
                    delay = float(response.headers.get('Retry-After',15))
                except (TypeError,ValueError):
                    delay = 15
                time.sleep(min(30,max(1,delay)))
                continue
            cause = {'openrouter_in_flight_budget':'동시 요청의 임시 비용 한도에 도달했습니다. 잠시 후 다시 실행해 주세요.',
                     'openrouter_key_limit':'API 키의 사용 한도에 도달했습니다. 키 한도를 확인해 주세요.',
                     'openrouter_credits':'현재 잔액으로 요청을 처리할 수 없습니다. 크레딧을 충전해 주세요.'}.get(
                         metadata.get('limit_source'),'잔액 또는 요청 비용 한도가 부족합니다. OpenRouter 크레딧을 확인해 주세요.')
            raise BillingError(f'OpenRouter 결제 한도(HTTP 402): {cause} 완료한 원문 분석은 보존됩니다.')
    if code in (400,401,403,404):
        if code == 400 and is_context_limit(detail):
            raise ContextLimitError(f'AI 입력 한도를 초과했습니다. 검토 범위를 나누어야 합니다. {detail}')
        raise ConfigurationError(f'OpenRouter 요청 설정 오류: {code} (HTTP {response.status_code}) · {detail}')
    if code >= 400:
        raise ProviderTransientError(f'OpenRouter 호출 실패: {code} · {detail}. 완료 결과는 보존됩니다.')
    try:
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError('Provider body must be an object')
        record_token_usage(body, model)
        if body.get('error'):
            code = str(body['error'].get('code', ''))
            if code == '402':
                raise BillingError('OpenRouter 응답 중 결제 한도에 도달했습니다. 완료 결과는 보존됩니다.')
            raise AnalysisError('OpenRouter가 응답 중 공급자 오류를 반환했습니다.')
        choice = body["choices"][0]
        if not isinstance(choice, dict):
            raise ValueError('Provider choice must be an object')
        message = choice['message']
        if not isinstance(message, dict):
            raise ValueError('Provider message must be an object')
        if message.get('refusal') or choice.get('finish_reason') == 'content_filter':
            raise RefusalError('AI 공급자가 응답을 거절했습니다. 공급자 거절 상태를 확인해 주세요.')
        if choice.get('finish_reason') == 'error':
            raise AnalysisError('AI 공급자가 응답 중 오류로 종료했습니다.')
        content = message['content']
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise AnalysisError("OpenRouter 응답 구조를 해석할 수 없습니다.") from exc
    if body['choices'][0].get('finish_reason') == 'length':
        raise OutputLimitError('응답이 출력 한도를 초과했습니다. 모든 필수 항목을 유지하며 설명을 간결하게 반환해야 합니다.')
    result = _extract_json(content)
    if response_schema is not None:
        try:
            validate_schema(result, response_schema)
        except ValueError as exc:
            raise AnalysisError(str(exc)) from exc
    return result, model

def analyze_document(file_name: str, text: str, *, upload_role: str | None = None) -> dict:
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
    candidates = result.get('section_matches')
    for item in (candidates if isinstance(candidates, list) else [])[:12]:
        if not isinstance(item, dict):
            continue
        if upload_role == 'evidence':
            quote = ''.join(str(item.get('evidence_quote', '')).split())
            if not quote or quote not in ''.join(excerpt.split()):
                continue
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
    from .document_classification import classify_content
    result["content_classification"] = classify_content(text, upload_role=upload_role)
    if upload_role == 'evidence':
        # Do not revive rejected mappings through ungrounded category labels.
        result['dac_criteria'] = sorted({m['slot_id'].split('-', 1)[0]
            for m in result['content_classification'].get('slot_matches', []) if m.get('confidence', 0) >= .45})
    if upload_role is not None:
        result['upload_role'] = upload_role
    from .document_classification import is_project_plan, pdm_slots
    if upload_role == 'project_plan' and not is_project_plan(result):
        raise AnalysisError('사업계획서의 배경·목표·추진계획을 확인하지 못했습니다. 올바른 사업계획서를 업로드해 주세요.')
    if upload_role == 'pdm' and not pdm_slots(result):
        raise AnalysisError('PDM의 목표·성과·검증지표를 확인하지 못했습니다. 실제 PDM 문서를 업로드해 주세요.')
    result["document_type"] = result["content_classification"]["document_type"]
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
