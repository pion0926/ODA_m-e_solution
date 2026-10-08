"""Bind grade-sheet cells to saved rule-based judgments by question identity."""
from backend.oda_me.hwpx.patchers import grade_question_reason

QUESTION_SLOTS = {
    'relevance': ('policy', 'adaptation'),
    'coherence': ('internal', 'external'),
    'effectiveness': ('output', 'outcome', 'equity'),
    'efficiency': ('timeliness', 'balance'),
    'sustainability': ('capacity', 'environment'),
}


def bind_grade_question_slots(slots, evaluations, normalize=lambda value: value):
    result = dict(slots)
    criteria = {row.get('criterion_id', row.get('id')): row for row in evaluations}
    def score_text(value):
        return '판정보류' if value is None else f'{float(value):g}점'
    for criterion_id, suffixes in QUESTION_SLOTS.items():
        criterion = criteria.get(criterion_id)
        if criterion is None:
            continue
        questions = {row.get('question_id'): row for row in criterion.get('question_assessments', [])}
        for index, suffix in enumerate(suffixes, 1):
            question = questions.get(f'{criterion_id}-q{index}', {})
            prefix = f'{criterion_id}_{suffix}'
            result[prefix + '_score'] = score_text(question.get('score'))
            # A saved finding belongs to the same question, avoiding shuffled
            # or invented rationales when several scores are deliberately held.
            finding = str(question.get('finding') or '').strip()
            if finding:
                result[prefix + '_reason'] = grade_question_reason(normalize(finding), 100)
            elif question.get('score') is None:
                result[prefix + '_reason'] = '질문별 판단 근거가 충분하지 않아 점수 확정을 보류함.'
        result[criterion_id + '_total_score'] = score_text(criterion.get('score'))
        result[criterion_id + '_total_reason'] = ''
    return result
