"""Keep totals, partial observations and identifiable events in separate scopes."""
import hashlib
import re
import unicodedata
from datetime import date


BASES = ('cumulative', 'period_total', 'individual_event', 'unspecified')


def compact(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()


def is_event_indicator(indicator):
    text = str(indicator.get('indicator') or indicator.get('text') or '')
    return bool(re.search(r'횟수|\(\s*회\s*\)', text))


def requires_scope_review(indicator):
    text = str(indicator.get('indicator') or indicator.get('text') or '')
    return bool(re.search(r'횟수|건수|인원|\(\s*(?:명|회|건|개|권|종)\s*\)', text))


def grounded_date(value, text):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value or ''):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    year, month, day = (int(part) for part in value.split('-'))
    return bool(re.search(rf'(?<!\d){year}\s*[-./년]\s*0?{month}\s*[-./월]\s*0?{day}(?!\d)', text))


def normalize_scope(raw, context, indicator, value, kind):
    """AI labels never authorize counting without grounded event identity."""
    raw = raw if isinstance(raw, dict) else {}
    basis = raw.get('basis') if raw.get('basis') in BASES else 'unspecified'
    label = str(raw.get('scope_label') or '').strip()
    if label and compact(label) not in compact(context):
        label = ''
    result = {'basis': basis, 'scope_label': label}
    unit = raw.get('period_unit')
    result['period_unit'] = unit if unit in {'project','year','month','day'} else 'unspecified'
    if basis != 'individual_event':
        return result
    name = str(raw.get('event_name') or '').strip()
    location = str(raw.get('event_location') or '').strip()
    day = str(raw.get('event_date') or '')
    end = str(raw.get('event_end_date') or day)
    valid = (kind == 'actual' and is_event_indicator(indicator) and compact(value) == '1회'
             and raw.get('event_completed') is True and grounded_date(day, context)
             and grounded_date(end, context) and end >= day
             and len(compact(name)) >= 3 and compact(name) in compact(context)
             and len(compact(location)) >= 2 and compact(location) in compact(context))
    if not valid:
        return {**result, 'basis': 'unspecified', 'warning': '개별 행사 식별·완료·날짜 근거가 불완전하여 자동 누적하지 않습니다.'}
    result.update(event_name=name, event_location=location, event_date=day, event_end_date=end, event_completed=True)
    result['event_identity'] = hashlib.sha256(f'{day}|{end}|{compact(name)}|{compact(location)}'.encode()).hexdigest()
    result['evidence_quote'] = context
    return result


def scoped_candidates(indicator, candidates):
    """Return comparable observations or None when adding/selecting would mix scopes."""
    if not candidates or any(item.get('kind') != 'actual' for item in candidates):
        return candidates, []
    scopes = [(item.get('measurement_scope') or {}) for item in candidates]
    bases = {scope.get('basis', 'unspecified') for scope in scopes}
    labels = {compact(scope.get('scope_label')) for scope in scopes if scope.get('scope_label')}
    if len(labels) > 1:
        return None, ['실적의 대상·지역·집계 범위가 달라 자동으로 비교하거나 합산하지 않았습니다.']
    if len(bases) > 1:
        cumulative = [item for item, scope in zip(candidates, scopes)
                      if scope.get('basis') == 'cumulative' and item.get('quote')
                      and item.get('document_id') and not item.get('previous_result')]
        if cumulative:
            # A proven cumulative subtotal remains useful even when the new event
            # might already be included. Do not let a prior unknown/zero hide it.
            return [{**item, 'aggregation_review_required':True} for item in cumulative], [
                '근거에서 확인한 누적 실적을 표시합니다. 추가 행사·기간 합계의 포함 여부가 불명확하여 더하지 않고 달성률 산정을 보류했습니다.']
        return None, ['누적 실적·기간 합계·개별 행사 또는 범위 미확인 값이 섞여 이전 실적을 유지하고 비교를 보류했습니다.']
    if bases == {'period_total'}:
        periods = {scope.get('period_unit', 'unspecified') for scope in scopes}
        if len(periods) > 1 or periods == {'unspecified'}:
            return None, ['월간·연간 등 집계 기간의 길이가 다르거나 불명확하여 총량을 직접 비교하지 않았습니다.']
    if bases != {'individual_event'}:
        return candidates, []
    if not is_event_indicator(indicator) or any(not scope.get('event_identity') for scope in scopes):
        return None, ['개별 행사 식별 근거가 부족하여 합산하지 않았습니다.']
    # Only complete, individually verified events qualify. A later duplicate upload
    # must not erase a second event or increase the total.
    if any(item.get('role_verification') != 'measurement-role-v2-scope' for item in candidates):
        return None, ['개별 행사 완료 사실의 독립 검증 전이므로 합산하지 않았습니다.']
    text = str(indicator.get('indicator') or indicator.get('text') or '')
    window = 7 if re.search(r'월별|월간|매월|월\s*평균', text) else 4 if re.search(r'연간|연도별|매년', text) else 0
    periods = [scope['event_date'][:window] if window else 'project' for scope in scopes]
    selected_period = max(periods)
    events = [(item, scope) for item, scope, period in zip(candidates, scopes, periods) if period == selected_period]
    groups = []
    for item, scope in sorted(events, key=lambda pair: pair[1]['event_date']):
        start, end = scope['event_date'], scope.get('event_end_date', scope['event_date'])
        if groups and start <= groups[-1]['end']:
            groups[-1]['end'] = max(end, groups[-1]['end'])
            groups[-1]['matches'].append((item, scope))
        else:
            groups.append({'start':start, 'end':end, 'matches':[(item, scope)]})
    notes = []
    unique = []
    for group in groups:
        day, matches = group['start'], group['matches']
        identities = {scope['event_identity'] for _, scope in matches}
        # Different titles/venues can still be one itinerary or parallel teams.
        # Preserve a conservative lower bound until a human separates same-day events.
        unique.append(matches[0][0])
        if len(identities) > 1:
            notes.append(f'{day}: 날짜가 겹치는 행사 기록은 별개 행사인지 확정할 수 없어 1회만 반영했습니다.')
    if len(events) > len(unique):
        notes.append('동일 날짜 행사에 대한 여러 문서는 중복 합산하지 않았습니다.')
    notes.append(f'완료 사실·행사명·장소·날짜를 검증한 개별 행사 {len(unique)}회 반영')
    selected = {**unique[-1], 'value': f'{len(unique)}회',
                'period': max(group['end'] for group in groups), 'aggregation_basis': 'distinct_verified_event_dates',
                'supporting_document_ids': sorted({str(item['document_id']) for item, _ in events}),
                'event_dates': [group['start'] for group in groups], 'aggregation_window': selected_period}
    return [selected], notes
