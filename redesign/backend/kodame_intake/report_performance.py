"""Reuse saved indicator decisions and bind report cells to their exact values."""
import re
from .document_eligibility import filter_performance_model


def performance_context(model, allowed_ids):
    filtered = filter_performance_model(model or {}, allowed_ids)
    rows = []
    for item in filtered.get('performance_indicators', []):
        row = {key: item.get(key) for key in ('id', 'tier_id', 'indicator', 'evidence', 'baseline', 'target', 'actual',
                'achievement_rate', 'achievement_label', 'measurement_status', 'status', 'note')}
        row['selected_sources'] = {kind: {key: source.get(key) for key in
            ('document_id', 'file_name', 'quote', 'value', 'period', 'measurement_scope',
             'supporting_document_ids', 'event_dates', 'aggregation_basis', 'aggregation_window',
             'aggregation_review_required')}
            for kind, source in (item.get('selected_measurements') or {}).items()}
        row['other_target_values'] = list(dict.fromkeys(str(o['value']) for o in item.get('measurement_sources', [])
            if o.get('kind') == 'target' and o.get('value') != item.get('target')))
        rows.append(row)
    return {'indicators': rows, 'rule': (
        '성과지표 모니터링에서 원문 검증·단위 검증 후 저장한 현재 선택값이다. 최신 PDM은 지표명·계층·MOV의 기준이며, '
        '목표·실적은 연결된 사업계획서와 실적 자료에서 보완된다. PDM 자체에 수치가 없다고 이 값을 미기재로 지우지 않는다. '
        '확인된 유/무 및 수치를 임의로 재판정하지 않는다. 충돌·미완료·실적 미확인을 0이나 달성으로 바꾸지 않는다. '
        '집계 실적은 supporting_document_ids의 개별 행사 근거와 event_dates·aggregation_basis를 함께 해석한다. '
        '대표 인용문 하나가 합산 수치를 직접 진술한 것처럼 서술하지 않는다. '
        '다른 목표값 및 기준일 미기재는 기간·범위의 한계로 설명한다. 사업 전체 성과와 개별 지표 달성을 구분한다.'
    )}


def source_ids(context):
    return list(dict.fromkeys(str(document_id)
        for item in context.get('indicators', []) for source in item.get('selected_sources', {}).values()
        for document_id in [source.get('document_id'), *(source.get('supporting_document_ids') or [])]
        if document_id))


def _line(value, fallback='확인 필요'):
    text = re.sub(r'\s+', ' ', str(value if value is not None else '')).strip()
    return fallback if text in {'', '-', '—'} else text


def achievement_records(context):
    result = []
    for item in context.get('indicators', []):
        if item.get('tier_id') not in {'outcome', 'output', 'outputs'}:
            continue
        state = item.get('measurement_status')
        if state == 'incomplete':
            comparison = '분석 미완료로 달성 판정 보류'
        elif state == 'conflict':
            comparison = '자료 간 충돌로 달성 판정 보류'
        elif item.get('achievement_label'):
            comparison = item['achievement_label']
        elif item.get('achievement_rate') is not None:
            comparison = f"{float(item['achievement_rate']):g}% (저장된 선택 목표 대비)"
        else:
            comparison = '비교 가능한 목표 또는 실적 부족으로 미산정'
        notes = ['저장된 성과지표 분석 결과를 반영함']
        if item.get('note'):
            notes.append(_line(item['note']))
        if item.get('other_target_values'):
            notes.append('다른 자료의 목표 ' + ', '.join(map(_line, item['other_target_values'])) + ': 기간·범위 차이 확인 필요')
        result.append(f"- [{item['id']}]: 성과지표: {_line(item.get('indicator'))} / 기초선: {_line(item.get('baseline'))} / "
            f"목표치: {_line(item.get('target'))} / 종료선 또는 현재 실적: {_line(item.get('actual'), '실적 미확인')} / "
            f"대비 결과: {comparison} / 지표입증수단(MOV): {_line(item.get('evidence'))} / 비고: {'; '.join(notes)}")
    return result


def bind_achievement(content, context):
    records = achievement_records(context)
    if not records:
        return content
    # Keep the model's interpretation, but never let it erase or re-infer the
    # already reviewed measurements. HWPX consumes these stable indicator IDs.
    heading = re.search(r'(?m)^\s*(?:#{1,6}\s*)?(?:3\.\s*종합\s*평가\s*및\s*시사점|ㅇ\s*성과\s*해석)\s*$', content)
    narrative = content[heading.end():].strip() if heading else ''
    if not narrative:
        narrative = ('ㅇ 저장된 목표·실적과 남은 근거 공백을 구분하여 해석함. 기준일 또는 자료 범위가 다른 목표는 '
                     '단순 합산하지 않으며, 미확인 실적은 0으로 간주하지 않음.')
    return '\n\n'.join(records) + '\n\n3. 종합 평가 및 시사점\n\n' + narrative
