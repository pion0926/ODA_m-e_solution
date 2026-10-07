"""One targeted expansion for DAC questions lacking direct evidence."""


def missing_ranges(length, ranges):
    cursor, gaps = 0, []
    for start, end in sorted(ranges):
        start, end = max(0, start), min(length, end)
        if start > cursor:
            gaps.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < length:
        gaps.append([cursor, length])
    return gaps


def escalation_questions(documents, question_ids):
    kinds = {qid: set() for qid in question_ids}
    for doc in documents:
        for chunk in (doc.get('fulltext_review') or {}).get('chunks', []):
            for fact in chunk['evidence']:
                if fact['question_id'] in kinds:
                    kinds[fact['question_id']].add(fact['kind'])
    # A limitation is useful evidence, not itself a contradiction or a reason
    # to reread the whole project. The assessor checks comparability/conflicts.
    return {qid: '직접 근거 부족: 관련 미검토 구간 추가 확인'
            for qid, values in kinds.items() if not values & {'positive', 'limitation'}}


def expand_documents(all_documents, reviewed, questions, *, review_plan=None):
    from .dac_review import text_for, select_ranges
    from .evaluation_criteria import EVALUATION_CRITERIA
    question_by_id = {q['id']: q for c in EVALUATION_CRITERIA.values() for q in c['questions']}
    by_id = {d['id']: d for d in reviewed}
    result = []
    for doc in all_documents:
        previous = by_id.get(doc['id'], doc)
        text = text_for(doc)
        scopes = dict(previous.get('question_scopes') or {})
        for qid, reason in questions.items():
            excluded = ((review_plan or {}).get('selection_overrides', {}).get(qid) or {}).get('excluded', [])
            if str(doc['id']) in excluded:
                # A user removal is a scope decision, not missing evidence to
                # undo automatically during the initial run or its resume.
                scopes.pop(qid, None)
                continue
            cid = qid.rsplit('-q', 1)[0]
            if qid not in question_by_id or (qid not in scopes and cid not in doc.get('assigned_criteria', [])):
                continue
            scope = scopes.get(qid, {})
            if scope.get('mode') == 'full':
                continue
            reviewed_ranges = scope.get('ranges', [])
            additional = select_ranges(text, question_by_id[qid], doc.get('analysis') or {},
                                       excluded_ranges=reviewed_ranges, max_blocks=3, fallback=False)
            if not additional:
                continue
            scopes[qid] = {**scope, 'mode': 'focused', 'ranges': sorted(reviewed_ranges + additional),
                           'reason': reason, 'escalated': True}
        if not scopes:
            continue
        result.append({**previous, 'question_scopes': scopes, 'scope_text': text,
                       'dac_fulltext_cache': previous.get('fulltext_review') or previous.get('dac_fulltext_cache'),
                       'review_all': False,
                       'assigned_criteria': sorted({q.rsplit('-q', 1)[0] for q in scopes})})
    return result
