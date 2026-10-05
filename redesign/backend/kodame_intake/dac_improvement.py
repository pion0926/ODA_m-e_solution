"""Read-only improvement guidance from the saved rubric trace, across projects.

No provider call, new score, inferred project fact, or mutation of an assessment.
Missing evidence and demonstrated poor outcomes deliberately produce different advice.
"""
VERSION = 'dac-improvement-v1'


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def build_improvement_guidance(criterion, *, stale=False):
    items = []
    seen = set()

    def add(question, kind, title, reason, action, required='', check=None):
        check = check or {}
        key = (_text(question.get('question_id')), _text(question.get('question')),
               _text(check.get('id')), title, reason, required)
        if key in seen:
            return
        seen.add(key)
        items.append({'kind': kind, 'title': title, 'reason': reason, 'action': action,
                      'required_evidence': required,
                      'question_id': _text(question.get('question_id')),
                      'question': _text(question.get('question')),
                      'check_id': _text(check.get('id')),
                      'evidence_document_ids': [x for x in check.get('evidence_document_ids', [])
                                                if isinstance(x, str)]
                      if isinstance(check.get('evidence_document_ids'), list) else []})

    for question in _objects(criterion.get('question_assessments')):
        trace = question.get('scoring_trace')
        if not isinstance(trace, dict) or not trace.get('rubric_digest'):
            add(question, 'review', '기준 적용 내역 확인',
                '이전 형식의 평가로 세부 기준 적용 내역을 확인할 수 없습니다.',
                '현재 자료와 질문별 연결을 검토한 뒤 DAC 평가를 실행해 보완 항목을 확인하세요.')
            continue
        for check in _objects(trace.get('checks')):
            state = check.get('state')
            title = _text(check.get('criterion')) or '세부 평가항목'
            finding = _text(check.get('finding')) or '저장된 판단 근거를 확인하세요.'
            required = _text(check.get('required_evidence'))
            if state == 'conflicted':
                kind, action = 'review', '서로 다른 수치·진술의 원출처, 작성 시점, 대상과 단위를 대조하고 정정 근거를 연결하세요.'
            elif state == 'unverified':
                kind, action = 'evidence', '먼저 기존 문서의 해당 근거를 연결하세요. 없으면 실제 확인 가능한 자료를 확보하세요. 자료 미확인은 성과 미달을 뜻하지 않습니다.'
            elif state in {'negative', 'limited', 'substantial'}:
                kind, action = 'performance', '확인된 미충족 내용을 검토해 실행 가능한 보완 조치의 담당자·기한을 정하고, 이행 결과를 측정해 근거를 남기세요. 평가기간 이후 조치는 후속 성과로 구분하세요.'
                # A sufficient outcome can be downgraded solely for weak evidence.
                if check.get('proposed_state') == 'verified' and state == 'substantial' and not check.get('measurements'):
                    kind, action = 'evidence', '완전충족 판단에 부족한 원출처·직접 입증·평가기간 적합성을 확인하고 해당 원문을 연결하세요.'
            elif state == 'verified':
                if check.get('valid_evidence') is not False:
                    continue
                kind, action = 'evidence', '성과를 입증하는 원자료의 출처·직접성·평가기간 적합성을 보완하세요.'
            else:
                kind, action = 'review', '저장된 판단 상태를 확인하고 현재 기준으로 재평가하세요.'
            add(question, kind, title, finding, action, required, check)
            for measurement in _objects(check.get('measurements')):
                metric = _text(measurement.get('metric')) or title
                if measurement.get('validation_error'):
                    add(question, 'evidence', f'{metric} · 원문 수치 확인',
                        _text(measurement.get('validation_error')),
                        '목표와 실적이 직접 표시된 원문 표·행을 각각 연결하세요. 검증되지 않은 제안 수치는 사용하지 않습니다.', required, check)
                elif measurement.get('comparable') is False or measurement.get('due') is False:
                    add(question, 'review', f'{metric} · 비교 조건 확인',
                        '정의·기간·대상·단위 또는 목표시점 조건이 충족되지 않았습니다.',
                        '동일한 기준으로 비교 가능한 자료를 확보하고, 목표시점 미도래 지표는 도래 후 검토하세요.', required, check)
        for cap in _objects(trace.get('applied_rules')):
            add(question, 'review', '점수 상한 조건 확인', _text(cap.get('reason')),
                '상한을 적용한 사실과 원출처를 확인하세요. 해소 가능한 문제는 조치 결과와 승인·검증 자료를 남기고, 해소할 수 없는 제약은 평가에 유지하세요.')
        gate = trace.get('four_point_gate')
        if isinstance(gate, dict) and gate.get('status') != 'met':
            add(question, 'review', '4점 필수 조건 확인', _text(gate.get('finding')),
                '저장된 필수 조건의 미확인·미충족 부분을 확인하고 직접 증빙과 실제 이행 여부를 검토하세요.')
        if not _objects(trace.get('checks')):
            add(question, 'review', '세부 판정 누락 확인', '저장된 세부 판정이 없습니다.',
                '자료와 질문별 연결을 확인한 뒤 DAC 평가를 다시 실행하세요.')

    if not _objects(criterion.get('question_assessments')):
        add({}, 'review', '질문별 평가 필요', '질문별 평가 결과가 없습니다.',
            '자료를 등록·연결한 뒤 DAC 평가를 실행하세요.')
    order = {'review': 0, 'evidence': 1, 'performance': 2}
    items.sort(key=lambda item: order[item['kind']])
    return {'version': VERSION, 'is_stale': bool(stale), 'items': items,
            'counts': {kind: sum(i['kind'] == kind for i in items) for kind in order},
            'notice': '저장된 평가 근거와 내부 기준에 따른 보완 안내입니다. 자료 추가만으로 점수 상승을 보장하지 않으며, 보완 후 DAC 평가를 직접 실행해야 점수에 반영됩니다.',
            'maintenance': not items}
