"""Target references survive changes to actual-evidence mappings, with provenance."""
import copy
import re
from pathlib import Path

from .measurement_dimensions import validate_dimension
from .performance_scope import compact

TARGET_SELECTION_VERSION = 'target-selection-v2-actual-context'


def target_policy_needs_review(indicator):
    return ((indicator.get('target_selection') or {}).get('version') != TARGET_SELECTION_VERSION
            and any(item.get('kind') == 'target' for item in indicator.get('measurement_sources', [])))


def _same_period(left, right):
    from .performance_delta import period_key
    if not left or not right:
        return True
    if period_key(left) and period_key(right):
        # A year goal may accompany an actual measured during that year. A later
        # plan must never retroactively become that actual's denominator.
        return left == right or left.startswith(right + '-') or right.startswith(left + '-')
    return compact(left) == compact(right)


def _target_identity(value):
    """Retain inequality semantics; 95% and 95% 이상 are not interchangeable."""
    match = re.fullmatch(r'\s*(\d[\d,]*(?:\.\d+)?)\s*(%|명|건|회|종|권|개)?\s*(이상|이하|초과|미만)?\s*', str(value or ''))
    if match:
        from decimal import Decimal
        return (Decimal(match[1].replace(',', '')), match[2] or '', match[3] or 'equal')
    return compact(value)


def select_target(indicator, candidates, actual):
    """Goals follow their authority/reporting scope, never the largest number."""
    policy = {'version':TARGET_SELECTION_VERSION, 'policy':'pdm_then_same_actual_context_then_consensus',
              'status':'unavailable'}
    official = indicator.get('pdm_target') or {}
    if official.get('origin') == 'pdm_explicit_target' and official.get('value'):
        return {**official,'kind':'target','indicator_id':indicator.get('id')}, {
            **policy,'status':'selected','basis':'pdm_explicit_target'}, []
    pool = candidates
    basis = 'reference_consensus'
    if actual and actual.get('document_id') and actual.get('quote'):
        same_report = [item for item in candidates if item.get('document_id') == actual['document_id']
                       and _same_period(item.get('period',''), actual.get('period',''))]
        actual_quote = compact(actual['quote'])
        same_row = [item for item in same_report if len(compact(item.get('quote'))) >= 8
                    and (compact(item['quote']) in actual_quote or actual_quote in compact(item['quote']))]
        if same_row or same_report:
            pool = same_row or same_report
            basis = 'same_actual_source_row' if same_row else 'same_actual_document_period'
    if not pool:
        return None, policy, []
    if len({_target_identity(item.get('value')) for item in pool}) != 1:
        return None, {**policy,'status':'review_required','basis':basis}, [
            '목표: 적용 기간·범위가 다른 목표를 높은 수치로 바꾸지 않았습니다. 공식 PDM 또는 선택 실적과 대응하는 목표 확인이 필요합니다.']
    chosen = pool[0]
    notes = []
    if basis.startswith('same_actual'):
        notes.append('목표: 선택한 실적과 같은 보고 자료의 목표를 적용했습니다. 다른 연도·계획의 목표는 별도 참고값으로 보존합니다.')
    if re.search(r'이상|이하|초과|미만', str(chosen.get('value'))):
        notes.append('목표의 이상·이하 등 조건을 원문대로 보존하며 단순 나눗셈 달성률로 환산하지 않습니다.')
    return chosen, {**policy,'status':'selected','basis':basis,'document_id':chosen.get('document_id'),
                    'value':chosen.get('value')}, notes


def reference_targets(documents, indicator, previous=None, text_cache=None, source_id=None):
    """Reuse grounded target facts; never turn planning documents into actuals."""
    text_cache = {} if text_cache is None else text_cache
    allowed = {str(document['id']) for document in documents}
    result = [copy.deepcopy(item) for item in (previous or {}).get('measurement_sources', [])
              if item.get('kind') == 'target' and str(item.get('document_id')) in allowed]
    for document in documents:
        matched_source = (((document.get('analysis') or {}).get('evidence_matches') or {}).get('sources') or {}).get('pdm') or {}
        if source_id and str(matched_source.get('id')) != str(source_id):
            continue
        facts = ((document.get('analysis') or {}).get('registration_facts') or {}).get('facts', [])
        facts = [fact for fact in facts if fact.get('kind') == 'target'
                 and indicator['id'] in fact.get('pdm_indicator_ids', [])
                 and fact.get('verification') == 'source_quote_verified'
                 and fact.get('scope') != 'sample_only']
        if not facts or not document.get('extracted_path'):
            continue
        try:
            path = document['extracted_path']
            if path not in text_cache:
                from .openrouter import redact_for_external_analysis
                raw_text = Path(path).read_text(encoding='utf-8')
                text_cache[path] = (compact(raw_text), compact(redact_for_external_analysis(raw_text)[0]))
            texts = text_cache[path]
        except (OSError, UnicodeError):
            continue
        for fact in facts:
            value = str(fact.get('value') or '').strip()
            quote = str(fact.get('evidence_quote') or '')
            if (not value or not compact(quote) or not any(compact(quote) in text for text in texts)
                    or compact(value) not in compact(quote)):
                continue
            unit = str(fact.get('unit') or '').strip()
            if unit and re.fullmatch(r'\d[\d,]*(?:\.\d+)?', value):
                value += unit
            observation = {'indicator_id': indicator['id'], 'kind':'target', 'value':value,
                           'quote':quote, 'period':str(fact.get('period') or ''),
                           'document_id':str(document['id']), 'file_name':document['original_name'],
                           'reference_role':'target_definition', 'registration_fact_id':fact.get('id'),
                           'target_authority':'reported_reference'}
            accepted, reason = validate_dimension(indicator, observation)
            if not reason:
                result.append(accepted)
    # Do not duplicate an existing verified target when registration finds it again.
    unique = {}
    for item in result:
        key = (item.get('document_id'), compact(item.get('value')), compact(item.get('quote')))
        unique[key] = {**item, 'reference_role':'target_definition'}
    return list(unique.values())


def reference_signature(references):
    return sorted({(str(item.get('document_id') or ''), compact(item.get('value')), compact(item.get('quote')))
                   for item in references if item.get('kind') == 'target'})
