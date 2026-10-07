"""Committed document/indicator history and deterministic incremental reconciliation."""
import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from .llm_models import current_llm_model


def fingerprint(source_id, document, indicator):
    payload=[str(source_id),str(document['id']),str(document.get('sha256') or ''),
             indicator['id'],indicator.get('text',indicator.get('indicator','')),indicator.get('mov',indicator.get('evidence',''))]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()


def history(previous, documents, indicators, source_id):
    if not previous or str(previous.get('source_document_id')) != str(source_id):
        return {}
    from .pdm_evidence import MEASUREMENT_VERSION
    model=previous['model']; saved=copy.deepcopy(model.get('monitoring',{}).get('pair_results',{}))
    allowed = {str(doc['id']) for doc in documents}
    saved = {key:value for key,value in saved.items() if str(value.get('document_id')) in allowed}
    from .measurement_dimensions import validate_dimension
    indicator_by_id = {item['id']: item for item in indicators}
    from .performance_scope import requires_scope_review
    # Revisit count pairs once when their old extraction did not distinguish a
    # cumulative total from a single event. Other valid pairs remain reusable.
    saved = {key: value for key, value in saved.items()
             if value.get('measurement_version') == MEASUREMENT_VERSION
             or not requires_scope_review(indicator_by_id.get(value.get('indicator_id'), {}))}
    from .measurement_semantics import needs_review
    document_by_id = {str(doc['id']):doc for doc in documents}
    saved = {key:value for key,value in saved.items() if value.get('measurement_version') in {MEASUREMENT_VERSION, 'pdm-evidence-v7-proposals', 'pdm-evidence-v6-roles'} or
             not needs_review(document_by_id.get(str(value.get('document_id')),{}),value.get('observations',[]))}
    saved = {key: value for key, value in saved.items() if all(
        validate_dimension(indicator_by_id.get(value.get('indicator_id'), {}), item) == (item, None)
        for item in value.get('observations', []))}
    # Old empty results had no per-indicator review and can contain false negatives.
    # Keep genuine measurements; recheck only unverified empty pairs once.
    saved={key:value for key,value in saved.items() if value.get('observations') or
           (value.get('measurement_version') in {MEASUREMENT_VERSION, 'pdm-evidence-v7-proposals', 'pdm-evidence-v6-roles', 'pdm-evidence-v4-recheck'} and value.get('reviews'))}
    old={i['id']:i for i in model.get('performance_indicators',[])}
    reviewed=model.get('monitoring',{}).get('reviewed_mappings',{})
    # Legacy measurements can be reused; unreviewed empty results must be rechecked.
    for indicator in indicators:
        prior=old.get(indicator['id'])
        if not prior or prior.get('measurement_status')=='incomplete': continue
        if prior.get('indicator') != indicator.get('text',indicator.get('indicator')) or prior.get('evidence') != indicator.get('mov',indicator.get('evidence')): continue
        for doc in documents:
            if str(doc['id']) not in reviewed.get(indicator['id'],[]): continue
            key=fingerprint(source_id,doc,indicator)
            if key not in saved and 'pair_results' not in model.get('monitoring',{}):
                observations=[o for o in prior.get('measurement_sources',[]) if o.get('document_id')==str(doc['id'])]
                if not observations:
                    continue
                saved[key]={'document_id':str(doc['id']),'indicator_id':indicator['id'],
                            'observations':observations,
                            'origin':'previous_committed_analysis'}
    return saved


def period_key(period):
    if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?',period or ''): return None
    parts=list(map(int,period.split('-')))
    try: date(parts[0],parts[1] if len(parts)>1 else 1,parts[2] if len(parts)>2 else 1)
    except ValueError: return None
    return tuple(parts+[0]*(3-len(parts)))


def comparison_baseline(indicator):
    """Send the relevant prior decisions, not every old quote and risk paragraph."""
    return {key: copy.deepcopy(indicator[key]) for key in
            ('id', 'indicator', 'evidence', 'target', 'actual', 'achievement_rate',
             'measurement_status', 'selected_measurements', 'pdm_target', 'target_review_required')
            if key in indicator}


def reconcile(indicator, observations, errors, prior=None):
    from .pdm_evidence import _compact, _number
    from decimal import Decimal, ROUND_HALF_UP
    from .measurement_dimensions import validate_dimension
    verified, rejected = [], []
    for observation in observations:
        accepted, reason = validate_dimension(indicator, observation)
        if reason:
            rejected.append({**observation, 'exclusion_reason': reason})
        else:
            verified.append(accepted)
    observations = verified
    indicator['measurement_sources']=observations
    indicator['excluded_measurements']=rejected
    for kind in ('target', 'actual'):
        if prior and any(o.get('kind')==kind for o in prior.get('measurement_sources',[])) and not any(o['kind']==kind for o in observations):
            # A successfully rechecked source can retract an earlier false positive.
            indicator[kind] = '-'
        prior_value = (indicator.get('selected_measurements') or {}).get(kind) or {'value': indicator.get(kind), 'quote': ''}
        if validate_dimension(indicator, prior_value)[1]:
            indicator[kind] = '-'
    selected={}; notes=[]; conflict=False
    indicator['aggregation_review_required'] = False
    prior_selected = copy.deepcopy(indicator.get('selected_measurements') or {})
    # Select the actual first so its reporting period/source can anchor a target.
    # The "latest then highest" rule applies to actuals, not to changing goals.
    for kind in ('actual','target'):
        candidates=[o for o in observations if o['kind']==kind]
        if kind == 'target':
            from .performance_targets import select_target
            chosen, target_selection, target_notes = select_target(indicator, candidates, selected.get('actual'))
            indicator['target_selection'] = target_selection
            notes.extend(target_notes)
            if chosen:
                indicator[kind] = chosen['value']; selected[kind] = chosen
            elif target_selection['status'] == 'review_required':
                indicator[kind] = '-'
                conflict = True
            elif kind in prior_selected and indicator.get(kind) == prior_selected[kind].get('value'):
                selected[kind] = prior_selected[kind]
            continue
        if not candidates:
            if kind in prior_selected and indicator.get(kind) == prior_selected[kind].get('value'):
                selected[kind] = prior_selected[kind]
            continue
        from .performance_scope import scoped_candidates
        candidates, scope_notes = scoped_candidates(indicator, candidates)
        notes.extend(scope_notes)
        if candidates is None:
            conflict = True
            if kind in prior_selected:
                selected[kind] = prior_selected[kind]
            continue
        if any(candidate.get('aggregation_review_required') for candidate in candidates):
            indicator['aggregation_review_required'] = True
            conflict = True
        # Different units are not comparable, even when a date is newer.
        units={_number(o['value'])[1] for o in candidates if _number(o['value'])}
        if len(units)>1:
            conflict=True; notes.append(f'{kind}: 단위가 달라 비교 확인 필요'); continue
        dated=[o for o in candidates if period_key(o.get('period',''))]
        if dated:
            latest=max(period_key(o['period']) for o in dated)
            pool=[o for o in dated if period_key(o['period'])==latest]
            if len(dated)<len(candidates): notes.append(f'{kind}: 기준일 미기재 자료는 최신일 비교에서 제외')
        else:
            pool=candidates; notes.append(f'{kind}: 기준일 미기재, 동일 단위 수치 우선 비교')
        numeric=[o for o in pool if _number(o['value'])]
        if len(numeric)==len(pool): chosen=max(numeric,key=lambda o:_number(o['value'])[0])
        elif len({_compact(o['value']) for o in pool})==1: chosen=pool[0]
        else:
            conflict=True; notes.append(f'{kind}: 동일 기준일의 정성값이 달라 확인 필요'); continue
        indicator[kind]=chosen['value']; selected[kind]=chosen
    indicator['selected_measurements']=selected
    indicator['measurement_status']='incomplete' if errors else 'conflict' if conflict else 'extracted' if observations else 'no_measurement'
    indicator['measurement_update']={'policy':'latest_period_then_highest_same_unit',
        'previous':{k:prior.get(k) for k in ('target','actual','achievement_rate')} if prior else None,
        'notes':notes,'errors':errors}
    target,actual=_number(indicator.get('target')),_number(indicator.get('actual'))
    indicator['achievement_rate']=None
    if not errors and not conflict and target and actual and target[0]>0 and target[1]==actual[1]:
        indicator['achievement_rate']=float((Decimal(str(actual[0]))/Decimal(str(target[0]))*100).quantize(Decimal('.1'),rounding=ROUND_HALF_UP))
    rate=indicator['achievement_rate']
    indicator['status']='unset' if rate is None else 'ok' if rate>=100 else 'watch' if rate>=70 else 'under'
    from .performance_status import apply_categorical_status
    apply_categorical_status(indicator)
    indicator['note']=' · '.join([*notes,*errors])


def enrich(performance, documents, plan, previous):
    from .pdm_evidence import extract_measurements
    if previous:
        from .document_eligibility import filter_performance_model
        previous = {**previous, 'model': filter_performance_model(previous['model'], [doc['id'] for doc in documents])}
    roster=[{**i,'text':i['indicator'],'mov':i['evidence']} for i in performance]
    records=history(previous,documents,roster,plan['source_document_id'])
    deferred = plan.get('deferred_mappings') or {}
    previous_records = ((previous or {}).get('model', {}).get('monitoring') or {}).get('pair_results') or {}
    for indicator in performance:
        for document in documents:
            if str(document['id']) not in deferred.get(indicator['id'], []):
                continue
            key = fingerprint(plan['source_document_id'], document, indicator)
            if key in previous_records:
                records[key] = copy.deepcopy(previous_records[key])
    same_source=previous and str(previous.get('source_document_id'))==str(plan['source_document_id'])
    old={i['id']:i for i in (previous or {}).get('model',{}).get('performance_indicators',[]) if same_source and any(
        current['id']==i['id'] and current['indicator']==i.get('indicator') and current['evidence']==i.get('evidence') for current in performance)}
    by_id={i['id']:i for i in performance}; errors={key:[] for key in by_id}
    changed=set(plan.get('mapping_changed_indicator_ids', [])) & set(by_id)
    from .performance_targets import reference_targets, reference_signature, target_policy_needs_review
    text_cache = {}
    targets_by_id = {}
    for indicator in performance:
        prior=old.get(indicator['id'])
        if prior and prior.get('indicator')==indicator['indicator']:
            keep={k:indicator[k] for k in ('id','indicator','evidence','evidence_document_ids')}
            if indicator.get('pdm_target'):
                keep['pdm_target'] = copy.deepcopy(indicator['pdm_target'])
            indicator.update(copy.deepcopy(prior)); indicator.update(keep)
            previous_ids = set((previous['model'].get('monitoring') or {}).get('reviewed_mappings', {}).get(
                indicator['id'], prior.get('evidence_document_ids', [])))
            previous_ids.update((previous['model'].get('monitoring') or {}).get('deferred_mappings', {}).get(indicator['id'], []))
            if previous_ids - set(deferred.get(indicator['id'], [])) != set(plan['mappings'].get(indicator['id'], [])):
                changed.add(indicator['id'])
        targets_by_id[indicator['id']] = reference_targets(documents, indicator, prior, text_cache,
                                                          source_id=plan['source_document_id'])
        previous_targets = (prior or {}).get('target_reference_sources', (prior or {}).get('measurement_sources', []))
        if reference_signature(targets_by_id[indicator['id']]) != reference_signature(previous_targets):
            changed.add(indicator['id'])
        if prior and target_policy_needs_review(prior):
            changed.add(indicator['id'])
    def analyze(doc):
        ids=[key for key,values in plan['new_mappings'].items() if str(doc['id']) in values]
        if not ids:return doc,ids,[],None
        baseline={key:comparison_baseline(old.get(key,{})) for key in ids}
        try:
            observations=extract_measurements(doc,[by_id[key] for key in ids],previous_evaluation=baseline)
            return doc,ids,observations,None
        except Exception as exc:
            return doc,ids,[],str(exc)[:200]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures=[executor.submit(copy_context().run,analyze,doc) for doc in documents if any(str(doc['id']) in ids for ids in plan['new_mappings'].values())]
        for future in futures:
            doc,ids,observations,error=future.result()
            for key in ids:
                changed.add(key)
                if error: errors[key].append(doc['original_name']+': '+error); continue
                indicator=by_id[key]
                review=(doc.get('analysis') or {}).get('pdm_measurements') or {}
                if key in review.get('unverified_indicator_ids',[]):
                    errors[key].append(doc['original_name']+': AI가 찾은 측정값의 원문 검증이 완료되지 않았습니다.')
                    continue
                from .pdm_evidence import MEASUREMENT_VERSION
                records[fingerprint(plan['source_document_id'],doc,indicator)]={
                    'document_id':str(doc['id']),'indicator_id':key,'observations':[o for o in observations if o['indicator_id']==key],
                    'measurement_version':MEASUREMENT_VERSION,
                    'reviews':[r for r in review.get('reviews',[]) if r['indicator_id']==key],
                    'model':current_llm_model(),'analyzed_at':datetime.now(timezone.utc).isoformat()}
    for key in changed:
        indicator=by_id[key]; observations=[]; reviews=[]
        effective_ids = set(plan['mappings'].get(key, [])) | set(deferred.get(key, []))
        old_actual_ids = {str(o.get('document_id')) for o in old.get(key, {}).get('measurement_sources', []) if o.get('kind') == 'actual'}
        if (old.get(key) and len(errors[key])==len(plan['new_mappings'][key]) and errors[key]
                and old_actual_ids <= effective_ids):
            indicator['measurement_status']='incomplete'
            indicator['measurement_update']={'policy':'latest_period_then_highest_same_unit','errors':errors[key],
                'notes':['신규 자료 분석 실패로 이전 성과 결과를 유지했습니다.']}
            indicator['note']='신규 자료 분석 미완료 · 이전 결과 유지: '+'; '.join(errors[key])
            continue
        for doc in documents:
            if str(doc['id']) in effective_ids:
                record=records.get(fingerprint(plan['source_document_id'],doc,indicator))
                if record:
                    observations.extend(record['observations'])
                    reviews.extend({'document_id':str(doc['id']),'file_name':doc['original_name'],**r} for r in record.get('reviews',[]))
        prior=old.get(key)
        # Older snapshots may predate pair_results, but only original observations
        # from an explicitly deferred, previously reviewed document are retained.
        for observation in (prior or {}).get('measurement_sources', []):
            if str(observation.get('document_id')) in deferred.get(key, []) and observation not in observations:
                observations.append(copy.deepcopy(observation))
        # An actual-evidence mapping does not define the target. A target quoted
        # from a still-eligible planning/reference document remains auditable even
        # when purpose review removes that document from actual-evidence mappings.
        target_references = targets_by_id[key]
        for observation in target_references:
            if observation not in observations:
                observations.append({**observation, 'reference_role': 'target_definition'})
        indicator['target_reference_sources'] = target_references
        indicator['target_review_required'] = bool(target_references and not indicator.get('pdm_target'))
        # Legacy reported values without document observations remain a dated/undated baseline.
        for kind in ('target','actual'):
            if (prior and not any(o['kind']==kind for o in prior.get('measurement_sources',[]))
                    and prior.get(kind) not in (None,'','-')
                    and (kind == 'target' or set(prior.get('evidence_document_ids', [])) <= effective_ids)):
                observations.append({'indicator_id':key,'kind':kind,'value':prior[kind],'period':'',
                                     'quote':'','document_id':'','file_name':'이전 평가 결과','previous_result':True})
        reconcile(indicator,observations,errors[key],prior)
        if indicator.get('target_review_required'):
            indicator['measurement_update']['notes'].append('목표는 활성 참고자료의 보고 목표입니다. PDM 공식 목표와의 일치 여부를 확인해 주세요.')
            indicator['note'] = ' · '.join([indicator.get('note', ''), '참고자료 목표 · PDM 목표 확인 필요']).strip(' ·')
        indicator['measurement_reviews']=reviews
        if indicator['measurement_status']=='no_measurement':
            reasons=list(dict.fromkeys(r.get('reason','') for r in reviews if r.get('reason')))
            indicator['note']='연결 문서 검토 완료 · 해당 지표의 직접 측정값 미확인' + (': '+'; '.join(reasons[:3]) if reasons else '')
    for indicator in performance:
        ids = deferred.get(indicator['id'], [])
        indicator['deferred_purpose_document_ids'] = list(ids)
        indicator['mapping_review_required'] = bool(ids)
        if ids:
            notice = '이전 증빙 연결은 목적 재검토 대기 중이며 기존에 확인한 결과를 참고값으로 보존했습니다.'
            if notice not in indicator.get('note', ''):
                indicator['note'] = (indicator.get('note', '') + ' · ' + notice).strip(' ·')
    return {'mapped_document_count':len({d for ids in plan['new_mappings'].values() for d in ids}),
            'new_pair_count':sum(map(len,plan['new_mappings'].values())),
            'restored_pair_count':sum(map(len,plan.get('restored_mappings', {}).values())),
            'observation_count':sum(len(i.get('measurement_sources',[])) for i in performance),
            'incomplete_indicator_count':sum(i.get('measurement_status')=='incomplete' for i in performance),'pair_results':records,'changed_indicator_ids':sorted(changed)}
