"""Versioned evidence rules. LLMs select facts; only this module computes scores."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from .dac_measurements import calculate

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'config/dac_evidence_rubric.json').exists())
RULES = json.loads((ROOT / 'config/dac_evidence_rubric.json').read_text(encoding='utf-8'))
VERSION = RULES['version']
RULE_DIGEST = hashlib.sha256(json.dumps(RULES, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
PROMPT_VERSION = 'dac-fact-judgement-v15-scope-conflict'
STATES = RULES['states']


def rounded(value, digits=1):
    return float(Decimal(str(value)).quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP))


def mean_score(values):
    if not values or any(v is None for v in values):
        return None
    return rounded(sum(Decimal(str(v)) for v in values) / len(values))


def definition(qid):
    return RULES['questions'][qid]


def _reason(value, location='판정'):
    if not isinstance(value, str) or len(value.strip()) < 12:
        raise ValueError(f'{location}: 12자 이상의 구체적 사실·한계 설명이 필요합니다. 받은 값: {value!r}')
    return value.strip()[:3000]


def refs_for(ids, evidence, qid):
    if not isinstance(ids, list) or any(not isinstance(i, str) or i not in evidence for i in ids):
        invalid=[i for i in ids if not isinstance(i,str) or i not in evidence] if isinstance(ids,list) else ids
        raise ValueError(f'{qid}: 존재하지 않는 증빙 ID를 참조했습니다: {invalid!r}. 제공된 evidence_id를 그대로 복사해야 합니다.')
    if any(evidence[i]['question_id'] != qid for i in ids):
        raise ValueError(f'{qid}: 다른 질문의 증빙을 사용했습니다.')
    return [evidence[i] for i in dict.fromkeys(ids)]


def _condition(item, evidence, qid, name):
    if not isinstance(item, dict) or item.get('status') not in {'met','not_met','unverified','conflicted'}:
        raise ValueError(f'{qid}: {name} 조건 상태가 잘못되었습니다.')
    found = refs_for(item.get('evidence_ids', []), evidence, qid)
    reason = _reason(item.get('finding'),f'{qid}.{name}.finding')
    if item['status'] == 'not_met' and not found:
        return {**item,'status':'unverified','proposed_status':'not_met','evidence_ids':[],
                'finding':reason+' 직접 인용이 없어 해당 조건의 미충족을 확정하지 않고 확인을 보류합니다.'}
    if item['status'] in {'met','not_met','conflicted'} and not found:
        raise ValueError(f'{qid}: {name} 판단에 원문 증빙이 필요합니다.')
    return {**item, 'finding': reason, 'evidence_ids':list(dict.fromkeys(item.get('evidence_ids',[])))}


def project_overruns(checks):
    """Only verified whole-project comparisons can constrain the budget question."""
    return [measurement for check in checks
            if check['id'] in {'FQ1_I01', 'FQ1_I02'} and check['valid_evidence']
            and check['state'] not in {'unverified', 'conflicted', 'not_due'}
            for measurement in check['measurements']
            if measurement.get('direction') in {'budget', 'duration'}
            and measurement.get('measurement_scope') == 'whole_project'
            and measurement.get('scope_validated') is True
            and measurement.get('comparable') is True and measurement.get('due') is True
            and not measurement.get('validation_error')
            and measurement.get('state') != 'unverified'
            and measurement.get('ratio') is not None and measurement['ratio'] >= 1.5]


def score_question(qid, item, evidence):
    rule = definition(qid)
    if item.get('question_id') != qid:
        raise ValueError('질문 ID가 정의와 일치하지 않습니다.')
    raw = item.get('indicators')
    if not isinstance(raw, list) or [x.get('indicator_id') for x in raw if isinstance(x, dict)] != [x['id'] for x in rule['checks']]:
        raise ValueError(f'{qid}: 5개 세부지표 ID와 순서를 정확히 유지해야 합니다.')
    checks = []
    for spec, fact in zip(rule['checks'], raw):
        state = fact.get('state')
        if state not in STATES:
            raise ValueError(f'{spec["id"]}: 허용되지 않는 상태입니다.')
        finding = _reason(fact.get('finding'),f'{spec["id"]}.finding')
        source_ids=list(fact.get('evidence_ids',[]))
        refs_for(source_ids,evidence,qid)
        for m in fact.get('measurements',[]):
            for key in ('target_evidence_ids','actual_evidence_ids','justification_evidence_ids'):
                ids=m.get(key,[])
                refs_for(ids,evidence,qid)
                source_ids.extend(ids)
        fact={**fact,'evidence_ids':list(dict.fromkeys(source_ids))}
        sources = refs_for(fact['evidence_ids'], evidence, qid)
        if state != 'unverified' and not sources:
            raise ValueError(f'{spec["id"]}: 미확인 외 판정에는 원문 인용이 필요합니다.')
        quality = dict(fact.get('quality') or {})
        for key in ('directness','recency'):
            if quality.get(key) in ('0','0.5','1'):
                quality[key]=float(quality[key])
        if state not in {'unverified','conflicted','not_due'}:
            if quality.get('source_grade') not in (1,2,3,4):
                raise ValueError(f'{spec["id"]}: 출처등급 1~4가 필요합니다.')
            if any(type(quality.get(k)) not in (int,float) or quality[k] not in (0,0.5,1) for k in ('directness','recency')):
                raise ValueError(f'{spec["id"]}: 직접성·시의성은 0/0.5/1이어야 합니다.')
            _reason(quality.get('rationale'),f'{spec["id"]}.quality.rationale')
        # Independence must identify the originating institution/data, not document counts.
        from .dac_corroboration import validated_families
        families, family_warnings = validated_families(
            fact.get('source_families', []), fact['evidence_ids'], evidence, qid)
        family_names = set()
        used_docs = set()
        for family in families:
            family_sources = refs_for(family.get('evidence_ids', []), evidence, qid)
            name = str(family.get('name') or '').strip().lower()
            family_names.add(name)
            used_docs.update(s['source_sha256'] for s in family_sources)
        independent = len(family_names) >= 2 and len(used_docs) >= 2
        grade = quality.get('source_grade', 1)
        ceiling = max((s.get('source_grade_ceiling',4) for s in sources),default=1)
        grade = min(grade,ceiling)
        if grade == 4 and not independent:
            grade = 3
        weights = RULES['dq_weights']
        dq = (weights['reliability'] * (0.5 if grade == 1 else 1)
              + weights['directness'] * quality.get('directness', 0)
              + weights['traceability'] * bool(sources) + weights['triangulation'] * independent
              + weights['recency'] * quality.get('recency', 0))
        if not sources:
            dq = 0
        applied = list(family_warnings)
        if ceiling == 1 and sources:
            applied.append('계획서·자체평가·타당성조사·PDM/실적 집계의 서술은 공식 원문·원시 측정자료 자체를 대신하지 못하므로 출처등급 최대 1 적용')
        effective = state
        negative_quote = str(fact.get('negative_fact_quote') or '').strip()
        if state == 'negative' and (len(negative_quote)<8 or not any(negative_quote in s['quote'] for s in sources)):
            effective = 'unverified'
            applied.append('직접적인 미실행·미달·피해 사실의 원문 발췌가 없어 미충족을 확정하지 않고 미확인으로 처리')
        measurements = calculate(fact.get('measurements',[]), evidence, qid, refs_for)
        if state == 'not_due' and any(m.get('due') is True for m in measurements):
            raise ValueError('목표시점 미도래 판정과 도래한 정량 측정치가 모순됩니다.')
        if not measurements and effective == 'verified' and spec['id'] in {'EQ1_I01','EQ2_I01','FQ1_I01','FQ1_I02'}:
            effective = 'substantial'
            applied.append('목표·실적 수치의 원문 대조 및 재계산 없이 정량 지표 완전충족 불가')
        for measurement in measurements:
            measurement_ids = {eid for key in ('target_evidence_ids','actual_evidence_ids','justification_evidence_ids')
                               for eid in measurement.get(key,[])}
            if not measurement_ids.issubset(fact.get('evidence_ids',[])):
                raise ValueError('정량 산식의 원문 증빙을 해당 지표 evidence_ids에도 포함해야 합니다.')
        if measurements and spec['id'] in {'EQ1_I01','EQ2_I01','FQ1_I01','FQ1_I02'}:
            # Keep missing/not-due measurements visible. No averaging away an unverified core metric.
            observed_measurements = [m for m in measurements if m['ratio'] is not None]
            if not observed_measurements:
                effective = 'not_due' if state == 'not_due' else 'unverified'
            elif state != 'conflicted':
                if spec['id'] in {'EQ1_I01','EQ2_I01'}:
                    ratio = sum(Decimal(str(m['ratio'])) for m in observed_measurements) / len(observed_measurements)
                    effective = 'verified' if ratio >= 1 else 'substantial' if ratio >= Decimal('.75') else 'limited' if ratio >= Decimal('.5') else 'negative'
                    if any(m['ratio'] < 1 for m in observed_measurements) and effective == 'verified':
                        effective = 'substantial'
                    applied.append('명시적 중요도 가중치가 없으므로 지표별 동일가중 평균; 120% 초과달성 상한 적용')
                else:
                    effective = min((m['state'] for m in observed_measurements),key=lambda s:STATES[s])
                if len(observed_measurements) != len(measurements) and effective == 'verified':
                    effective = 'substantial'
                applied.append('동일 기간·대상·단위의 목표/실적 원문 수치를 서버가 재계산; 핵심 미달 보존')
        invalid_measurements=[m for m in measurements if m.get('validation_error')]
        if invalid_measurements:
            effective='unverified'
            finding='정량 비교 수치를 지정된 원문에서 검증하지 못해 이 항목의 판정을 보류합니다. '+' '.join(m['validation_error'] for m in invalid_measurements)
            applied.append('원문에서 확인할 수 없는 제안 수치는 점수·성과 판단에서 제외하고 항목을 미확인으로 전환')
        if effective == 'verified' and grade < spec.get('min_grade_for_verified',2):
            applied.append('성과 충족 판단은 유지하되 출처 신뢰도 부족을 별도로 표시; 공식 확정평가가 아닌 잠정 진단')
        merit = STATES[effective]
        valid = merit is not None and dq >= RULES['valid_dq_min']
        checks.append({**spec, 'state': effective, 'proposed_state': state,
            'status': {'negative':'not_met','limited':'partial','substantial':'partial','verified':'met',
                       'unverified':'unverified','conflicted':'conflicted','not_due':'not_due'}[effective],
            'finding': finding, 'merit': merit, 'dq': rounded(dq, 3), 'valid_evidence': valid,
            'quality': {**quality, 'effective_source_grade':grade, 'independent_corroboration':independent},
            'source_families':families, 'applied_rules':applied, 'measurements':measurements,
            'negative_fact_quote':negative_quote,
            'evidence_ids':list(dict.fromkeys(fact.get('evidence_ids', []))),
            'evidence_document_ids': sorted({s['document_id'] for s in sources}),
            'evidence_document_refs': sorted({s['document_ref'] for s in sources})})
    gate = _condition(item.get('four_point_gate'), evidence, qid, '4점 필수')
    cap = _condition(item.get('specific_cap'), evidence, qid, '추가 상한')
    flag = _condition(item.get('red_flag'), evidence, qid, '중대한 부정적 영향')
    overruns = project_overruns(checks) if qid == 'efficiency-q1' else []
    if qid == 'efficiency-q1' and flag['status'] == 'met' and not any(
            m.get('justification') != 'verified' for m in overruns):
        raise ValueError('효율성 예산·기간 적색신호에는 동일 범위·도래 시점의 전체 사업 150% 이상 초과와 '
                         '타당한 사유가 없다는 직접 근거가 필요합니다. 비목·연차·개별 계약 초과 또는 '
                         '승인자료 미확인만으로 met를 선택하지 마세요.')
    conflict = any(c['state'] == 'conflicted' for c in checks) or any(c['status'] == 'conflicted' for c in (gate,cap,flag))
    observed = [c for c in checks if c['merit'] is not None]
    weight = sum(c['weight'] for c in observed)
    merit = sum(Decimal(str(c['merit'])) * c['weight'] for c in observed) / weight * 100 if weight else None
    eligible_weight = sum(c['weight'] for c in checks if c['state'] != 'not_due')
    coverage = sum(c['weight'] for c in checks if c['valid_evidence']) / eligible_weight if eligible_weight else 0
    dq = sum(c['dq'] * c['weight'] for c in observed) / weight if weight else 0
    confidence = 100 * (0.55 * coverage + 0.45 * dq)
    base = 1 + sum(merit >= Decimal(str(t)) for t in RULES['merit_thresholds']) if merit is not None else None
    caps = []
    if coverage < RULES['coverage_four']:
        caps.append({'rule':'COVERAGE_CAP', 'maximum':3, 'reason':'근거 확보율 85% 미만'})
    if gate['status'] != 'met' or any(c['state'] != 'verified' for c in checks):
        caps.append({'rule':'FOUR_POINT_GATE', 'maximum':3, 'reason':rule['gate']})
    if any(c['state']=='verified' and c['quality']['effective_source_grade'] < c.get('min_grade_for_verified',2) for c in checks):
        caps.append({'rule':'FOUR_POINT_CONFIDENCE', 'maximum':3,
                     'reason':'성과 충족 판단은 유지하지만 최고 4점에는 추가 출처 검증이 필요함'})
    if cap['status'] == 'met':
        caps.append({'rule':'QUESTION_CAP', 'maximum':2 if qid == 'relevance-q2' else 3, 'reason':rule['cap_condition']})
    if flag['status'] == 'met':
        caps.append({'rule':'NEGATIVE_RED_FLAG', 'maximum':1, 'reason':rule['red_flag_condition']})
    for m in overruns:
        # A missing approval is uncertainty, not proof of unjustified overrun.
        # The one-point red flag above requires the model to support the actual
        # adverse condition; acknowledged/approved overrun has its own ceiling.
        if m.get('justification') == 'verified' or flag['status'] == 'met':
            caps.append({'rule':'BUDGET_DURATION_150',
                         'maximum':2 if m['justification']=='verified' else 1,
                         'reason':'전체 사업 예산·기간 150% 이상을 동일 범위 원문으로 검증; '
                                  + ('승인·불가피성 확인' if m['justification']=='verified' else '타당한 사유 없음이 직접 확인됨')})
    status = ('conflicted' if conflict else 'needs_evidence' if coverage < RULES['coverage_min']
              else 'needs_review' if confidence < RULES['confidence_min'] else 'proposed')
    score = min([base]+[c['maximum'] for c in caps]) if base is not None and status == 'proposed' else None
    gaps = [f"{c['criterion']}: {c['required_evidence']}" for c in checks if c['state'] not in ('verified','not_due')]
    reason = (f"관측 {len(observed)}/5개, 근거 확보율 {coverage*100:.0f}%, 증거 신뢰도 {confidence:.1f}%. "
              + (f"성과지수 {float(merit):.1f} → 기본 {base}점. " if merit is not None else '판단 가능한 성과 근거 없음. ')
              + (f"상한 적용 후 {score}점." if score is not None else '자료 미확인 또는 충돌로 점수 판정 보류.'))
    return {'version':VERSION,'rubric_digest':RULE_DIGEST,'label':RULES['label'],'notice':RULES['notice'],
            'question_id':qid, 'levels':rule['official_levels'], 'checks':checks, 'selected_score':score,
            'selected_level_reason':reason, 'next_level_gap':' / '.join(gaps) or '검증된 성과와 증빙을 유지하고 후속 측정 필요',
            'status':status, 'merit_index':rounded(merit) if merit is not None else None,
            'coverage':rounded(coverage,3),'evidence_dq':rounded(dq,3),'confidence':rounded(confidence),
            'assessment_basis':'provisional_document_review',
            'timing':{'not_due_count':sum(c['state']=='not_due' for c in checks),
                      'unverified_count':sum(c['state']=='unverified' for c in checks),
                      'scored_count':len(observed)},
            'base_score':base,'applied_rules':caps,'four_point_gate':gate,'specific_cap':cap,'red_flag':flag}
