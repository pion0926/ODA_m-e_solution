"""Extract grounded measurements from every mapped document, with content caching."""
from __future__ import annotations
from .ai.prompt_registry import load_prompt

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import httpx

from psycopg.types.json import Jsonb

from .db import connection
from .openrouter import AnalysisError, MissingApiKey, _request_json, redact_for_external_analysis

MEASUREMENT_VERSION = 'pdm-evidence-v8-scope'

MEASUREMENT_PROMPT = load_prompt("performance_measurements")


def measurement_schema(indicators, sources=None):
    def obj(properties):
        return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    ident={'type':'string','enum':[i['id'] for i in indicators]}
    string={'type':'string'}
    reference = {'quote': string} if sources is None else {'source_id': {'type': 'string', 'enum': list(sources)}}
    from .performance_scope import BASES
    scope = obj({'basis': {'type':'string', 'enum':list(BASES)}, 'scope_label':string,
                 'period_unit':{'type':'string','enum':['project','year','month','day','unspecified']},
                 'event_name':string, 'event_date':string, 'event_end_date':string, 'event_location':string,
                 'event_completed':{'type':'boolean'}})
    context = {} if sources is None else {'context_source_ids':{'type':'array','items':{'type':'string','enum':list(sources)}}}
    return obj({'observations':{'type':'array','items':obj({'indicator_id':ident,
        'kind':{'type':'string','enum':['actual','target']},'value':string,**reference,**context,'period':string,
        'measurement_scope':scope})},
        'reviews':{'type':'array','items':obj({'indicator_id':ident,
            'status':{'type':'string','enum':['found','no_measurement']},'reason':string})}})


def _compact(value):
    return re.sub(r"\s+", "", str(value or ""))


def _number(value):
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(%|명|건|회|종|권|개)?\s*", str(value).replace(",", ""))
    return (float(match[1]), match[2] or "") if match else None


def _request_measurements(system_prompt, user_prompt, title, *, response_schema=None):
    for attempt in range(3):
        try:
            payload, model = _request_json(system_prompt, user_prompt, title, response_schema=response_schema)
            if not isinstance(payload.get("observations"), list):
                raise AnalysisError("PDM 측정값 응답에 observations 배열이 없습니다.")
            if response_schema:
                expected=set(response_schema['properties']['reviews']['items']['properties']['indicator_id']['enum'])
                reviews=payload.get('reviews',[])
                if {r.get('indicator_id') for r in reviews} != expected or len(reviews)!=len(expected):
                    raise AnalysisError('PDM 지표별 검토 결과가 누락되거나 중복되었습니다.')
            return payload, model
        except (AnalysisError, httpx.HTTPError):
            if attempt == 2:
                raise
            user_prompt += (
                '\n[JSON 형식 교정 요청] 이전 응답을 파싱할 수 없습니다. 모든 속성 이름의 앞뒤에 반드시 큰따옴표를 사용하세요. '
                'period: 또는 period": 는 잘못된 JSON입니다. "period": ""처럼 반환하세요. '
                '문자열 내 줄바꿈은 이스케이프하세요. 본문의 수치와 인용은 그대로 검증하고 JSON 문법만 정확히 작성하세요. '
                '정상 응답 구조: {"observations": [{"indicator_id": "지표 id", "kind": "actual", '
                '"value": "원문 값", "quote": "원문 인용", "period": ""}]}'
            )


def extract_measurements(document, indicators, *, previous_evaluation=None):
    from .llm_models import current_llm_model
    text = Path(document["extracted_path"]).read_text(encoding="utf-8")
    if not text.strip():
        raise AnalysisError("추출된 본문이 비어 있습니다.")
    roster = [{"id": i["id"], "indicator": i["indicator"], "evidence": i["evidence"]} for i in indicators]
    digest = hashlib.sha256((MEASUREMENT_VERSION + current_llm_model() + text + json.dumps(roster, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
    if previous_evaluation is not None:
        digest=hashlib.sha256((digest+json.dumps(previous_evaluation,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    analysis = document.get('analysis') or {}
    cache = dict(analysis.get('pdm_measurement_cache') or {})
    cached = cache.get(digest) or analysis.get("pdm_measurements", {})
    if cached.get("digest") == digest and not cached.get('unverified_indicator_ids'):
        document['analysis'] = {**analysis, 'pdm_measurements':cached}
        return cached["observations"]
    observations = []
    rejected_observations = []
    reviews = []
    rechecks = []
    # Cover the complete extracted text, including the end of long documents.
    for offset in range(0, len(text), 28000):
        chunk, _ = redact_for_external_analysis(text[max(0, offset - 1000):offset + 28000])
        from .intake_facts import reference_blocks
        sources = reference_blocks(chunk)
        source_prompt = [{'source_id': key, 'text': value} for key, value in sources.items()]
        payload, _ = _request_measurements(
            MEASUREMENT_PROMPT,
            json.dumps({"indicators": roster, "previous_evaluation":previous_evaluation or {},
                        "registration_fact_candidates": [f for f in ((document.get('analysis') or {}).get('registration_facts') or {}).get('facts', [])
                            if set(f.get('pdm_indicator_ids', [])) & {i['id'] for i in indicators}
                            and _compact(f.get('evidence_quote', '')) in _compact(chunk)],
                        "registration_fact_policy":"등록 사실은 탐색 후보다. 현재 원문과 측정 대상·단위·기간을 다시 확인한다. 후보에 없다는 이유로 원문 내용을 배제하지 않는다.",
                        "comparison_policy":"이전 평가를 비교 맥락으로만 사용한다. 신규 observations에는 현재 문서에서 직접 입증되는 값만 기록한다. 이전 값을 현재 문서의 근거로 인용하지 않는다. 같은 측정대상·범위·단위인지 확인하고, 겹치는 값은 명시된 최신 실적 기준일 다음 높은 수치를 우선 비교한다.",
                        "file_name": document["original_name"], "sources": source_prompt}, ensure_ascii=False),
            "KODAME PDM Evidence Measurements",
            response_schema=measurement_schema(indicators, sources),
        )
        from .measurement_recheck import suspicious_negatives
        suspects = suspicious_negatives(indicators, chunk, payload,
            ((document.get('analysis') or {}).get('registration_facts') or {}).get('facts', []))
        if suspects:
            second, _ = _request_measurements(MEASUREMENT_PROMPT +
                '\n독립 재검토: 선행 분석 결과를 추정하지 말고 표·동등 표현·단위·측정 연도를 처음부터 검토한다. '
                '목표·기초선과 실적을 구별하고 현재 원문에 직접 존재하는 값만 반환한다.',
                json.dumps({'indicators': suspects, 'sources': source_prompt}, ensure_ascii=False),
                'KODAME Independent Measurement Review', response_schema=measurement_schema(suspects, sources))
            payload['observations'].extend(second['observations'])
            rechecks.append({'start': max(0, offset-1000), 'end': min(len(text),offset+28000),
                             'indicator_ids': [i['id'] for i in suspects], 'reviews': second['reviews']})
            replaced = {i['id'] for i in suspects}
            payload['reviews'] = [r for r in payload.get('reviews', []) if r['indicator_id'] not in replaced] + second['reviews']
        reviews.extend({**r,'start':max(0,offset-1000),'end':min(len(text),offset+28000)} for r in payload.get('reviews',[]))
        items = payload.get("observations")
        if not isinstance(items, list):
            raise AnalysisError("PDM 측정값 응답에 observations 배열이 없습니다.")
        chunk_observations = []
        for item in items:
            if not isinstance(item, dict) or item.get("indicator_id") not in {i["id"] for i in indicators}:
                continue
            quote = str(sources.get(item['source_id'], '') if isinstance(item.get('source_id'),str) else item.get('quote') or '')
            value = str(item.get("value") or "").strip()
            if item.get("kind") not in {"actual", "target"} or not quote or _compact(quote) not in _compact(chunk):
                rejected_observations.append({**item,'exclusion_reason':'제안한 원문 출처 또는 측정값 종류를 확인하지 못했습니다.'})
                continue
            indicator = next(i for i in indicators if i['id'] == item['indicator_id'])
            context_quotes = [quote, *(sources[key] for key in item.get('context_source_ids', [])
                                      if isinstance(key, str) and key in sources)]
            from .performance_scope import normalize_scope
            scope = normalize_scope(item.get('measurement_scope'), '\n'.join(dict.fromkeys(context_quotes)),
                                    indicator, value, item['kind'])
            # Accept only explicitly quoted numbers / qualitative values.
            numeric = _number(value)
            if numeric:
                quoted_numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", quote)]
                # An individually identified completed event is one event, even
                # when its narrative never writes the aggregate phrase "1회".
                event_count = numeric == (1, '회') and scope.get('event_identity')
                if numeric[0] not in quoted_numbers and not event_count:
                    rejected_observations.append({**item,'exclusion_reason':'제안한 수치가 선택한 원문에 없습니다.'})
                    continue
            else:
                categorical = re.search(r'\(\s*유\s*/\s*무\s*\)', indicator.get('indicator', ''))
                # An exact foreign-language approval quote need not contain its
                # normalized Korean yes/no label. The source itself stays exact.
                normalized_category = categorical and value in {'유', '무'}
                if not value or (not normalized_category and _compact(value) not in _compact(quote)):
                    rejected_observations.append({**item,'exclusion_reason':'제안한 정성값을 선택한 원문에서 확인하지 못했습니다.'})
                    continue
            period=str(item.get('period') or '')
            from .performance_delta import period_key
            if not period_key(period) or not re.search(r'(?<!\d)'+r'\s*[-./년월\s]\s*'.join(map(re.escape,period.split('-')))+r'(?!\d)',chunk):
                period=''
            observation = {"indicator_id": item["indicator_id"], "kind": item["kind"], "value": value,
                "quote": quote, "period": period,
                "document_id": str(document["id"]), "file_name": document["original_name"],
                "measurement_scope":scope}
            if scope.get('event_identity'):
                observation['period'] = scope['event_date']
                observation['value_origin'] = 'identified_completed_event'
            from .measurement_dimensions import validate_dimension
            observation, reason = validate_dimension(next(i for i in indicators if i['id'] == item['indicator_id']), observation)
            if reason:
                rejected_observations.append({**item, 'exclusion_reason': reason})
                continue
            if observation not in chunk_observations:
                chunk_observations.append(observation)
        from .measurement_semantics import verify
        chunk_observations, semantic_rejections = verify(document, roster, sources, chunk_observations, _request_json)
        rejected_observations.extend(semantic_rejections)
        for observation in chunk_observations:
            if observation not in observations:
                observations.append(observation)
    verified_ids={o['indicator_id'] for o in observations}
    proposal_only = {r['indicator_id'] for r in reviews if r.get('status')=='found'} - verified_ids
    for review in reviews:
        if review['indicator_id'] in proposal_only:
            reasons = list(dict.fromkeys(o['exclusion_reason'] for o in rejected_observations if o['indicator_id']==review['indicator_id']))
            review.update(status='no_measurement', reason='AI 제안을 검토했지만 확인된 측정값은 없습니다. ' + '; '.join(reasons[:3]),
                          verification_warning=True)
    # Invalid suggestions are evidence limitations, not failed AI generation.
    # Preserve reasons for human review; only request/response failures abort a pair.
    unverified_ids=[]
    review_data={'digest':digest,'version':MEASUREMENT_VERSION,'model':current_llm_model(),
                 'observations':observations,'rejected_observations':rejected_observations,'reviews':reviews,'independent_rechecks':rechecks,'unverified_indicator_ids':unverified_ids}
    document.setdefault('analysis', {})
    if document['analysis'] is None:
        document['analysis']={}
    document['analysis']['pdm_measurements']=review_data
    cache.pop(digest, None)
    cache[digest] = review_data
    cache = dict(list(cache.items())[-4:])
    document['analysis']['pdm_measurement_cache'] = cache
    with connection() as conn:
        conn.execute("UPDATE intake_documents SET analysis=jsonb_set(jsonb_set(COALESCE(analysis,'{}'::jsonb),'{pdm_measurements}',%s),'{pdm_measurement_cache}',%s) WHERE id=%s",
                     (Jsonb(review_data), Jsonb(cache), document["id"]))
    return observations


def apply_measurements(indicator, observations, errors):
    indicator["measurement_sources"] = observations
    notes = []
    conflict = False
    for kind in ("target", "actual"):
        candidates = [o for o in observations if o["kind"] == kind]
        if not candidates:
            continue
        values = {_compact(o["value"]) for o in candidates}
        # Different scopes/dates need review; never equate upload order with measurement recency.
        if len(values) != 1:
            conflict = True
            indicator[kind] = "-"
            notes.append(f"{kind} 자료 간 값 불일치: " + ", ".join(sorted(values)))
            continue
        candidate = candidates[0]
        existing = str(indicator.get(kind) or "-")
        if existing not in ("", "-") and _compact(existing) != _compact(candidate["value"]):
            conflict = True
            indicator[kind] = "-"
            notes.append(f"{kind} 기존 실적표({existing})와 증빙({candidate['value']}) 대조 필요")
            continue
        indicator[kind] = candidate["value"]
        if not candidate["period"]:
            notes.append("측정기간 미기재: 확인 필요")
    if errors:
        notes.append("일부 증빙 내용 분석 미완료: " + "; ".join(errors))
    if observations or errors:
        indicator["achievement_rate"] = None
        target, actual = _number(indicator.get("target")), _number(indicator.get("actual"))
        if not conflict and not errors and target and actual and target[0] > 0 and target[1] == actual[1]:
            indicator["achievement_rate"] = float((Decimal(str(actual[0])) / Decimal(str(target[0])) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        rate = indicator["achievement_rate"]
        indicator["status"] = "unset" if rate is None else "ok" if rate >= 100 else "watch" if rate >= 70 else "under"
        indicator["measurement_status"] = "incomplete" if errors else "conflict" if conflict else "extracted"
        indicator["note"] = " · ".join(dict.fromkeys(filter(None, [indicator.get("note", ""), *notes])))


def enrich_from_evidence(performance, documents, assignments):
    by_id = {i["id"]: i for i in performance}
    observations = {key: [] for key in by_id}
    errors = {key: [] for key in by_id}
    mapped = {}
    for document_id, indicator_id, *_ in assignments:
        mapped.setdefault(str(document_id), set()).add(indicator_id)
    for indicator in performance:
        for document_id in indicator.get("evidence_document_ids", []):
            mapped.setdefault(str(document_id), set()).add(indicator["id"])
    def analyze(document):
        ids = sorted(mapped.get(str(document["id"]), set()) & by_id.keys())
        if not ids:
            return document, ids, [], None
        try:
            if not document.get("extracted_path"):
                raise OSError("추출된 본문 없음")
            return document, ids, extract_measurements(document, [by_id[key] for key in ids]), None
        except (OSError, UnicodeError, AnalysisError, MissingApiKey, httpx.HTTPError) as exc:
            return document, ids, [], str(exc)[:150]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(copy_context().run, analyze, document) for document in documents]
        for future in futures:
            document, ids, extracted, error = future.result()
            for key in ids:
                by_id[key]["evidence_document_ids"] = list(dict.fromkeys([*by_id[key].get("evidence_document_ids", []), str(document["id"])]))
                if error:
                    errors[key].append(document["original_name"] + ": " + error)
            for observation in extracted:
                observations[observation["indicator_id"]].append(observation)
    for key, indicator in by_id.items():
        apply_measurements(indicator, observations[key], errors[key])
    return {"mapped_document_count": len(mapped), "observation_count": sum(map(len, observations.values())),
            "incomplete_indicator_count": sum(bool(value) for value in errors.values())}
