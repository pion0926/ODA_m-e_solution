"""Reuse validated DAC decisions without resending their full raw corpus.

Original quotes and scoring traces remain immutable in criterion_evaluations.
The report has a separate source-evidence packet for new prose claims.
"""
from copy import deepcopy
import re


PROVISIONAL_BASIS = 'provisional_document_review'
PROVISIONAL_NOTICE = (
    '현재 등록 자료 기준의 내부 잠정 진단이며, KOICA·국무조정실의 공식 확정평가를 의미하지 않음. '
    '성과 수준·증빙 신뢰도·평가 시점을 구분하여 해석함.'
)


def is_provisional(evaluations):
    """Keep the saved scoring policy when projecting a decision into a report."""
    return any(
        row.get('assessment_basis') == PROVISIONAL_BASIS or
        any((question.get('scoring_trace') or {}).get('assessment_basis') == PROVISIONAL_BASIS
            for question in row.get('question_assessments', []))
        for row in evaluations
    )


def qualify_grade_slots(slots, evaluations):
    result = dict(slots)
    if not is_provisional(evaluations):
        return result
    for key in ('overall_score', 'koica_grade', 'government_grade'):
        value = str(result.get(key) or '').strip()
        if value and value != '판정보류' and '잠정' not in value:
            result[key] = value + ' (잠정)'
    return result


def qualify_report_text(part_id, content, evaluations):
    """Label an internal diagnosis without changing its scores or findings."""
    if not is_provisional(evaluations):
        return content
    if part_id == 'grade':
        from backend.oda_me.reports.context import parse_structured_section_slots, structured_slots_to_json
        slots = parse_structured_section_slots(content, 'grade')
        if slots:
            return structured_slots_to_json('grade', qualify_grade_slots(slots, evaluations))
    if part_id not in {'grade', 'summary-ko', 'conclusion'} and not part_id.startswith('criteria-'):
        return content
    value = re.sub(r'공식\s*(종합판정|종합점수|평가점수|평가등급)', r'잠정 \1', str(content or ''))
    value = re.sub(r'공식\s*((?:KOICA|코이카|국무조정실)\s*(?:평가)?등급)', r'참고 \1', value)
    value = value.replace('공식 등급표에 따른 판정', '등급표를 참고한 잠정 판정')
    if PROVISIONAL_NOTICE not in value:
        value = value.rstrip() + '\n\n- ' + PROVISIONAL_NOTICE
    return value


def for_report(evaluations):
    result = deepcopy(evaluations)
    for criterion in result:
        if is_provisional([criterion]):
            criterion['report_assessment_basis'] = PROVISIONAL_BASIS
            criterion['report_assessment_notice'] = PROVISIONAL_NOTICE
        for question in criterion.get('question_assessments', []):
            quotes = question.pop('evidence_quotes', [])
            question['validated_source_references'] = [
                {key: source[key] for key in ('evidence_id', 'document_id', 'file_name', 'locator', 'kind')
                 if key in source} for source in quotes
            ]
            question['evidence_use_rule'] = (
                '서버에서 원문 대조·계산을 완료한 판정이다. 점수·보류·수치·한계를 그대로 사용한다. '
                '출처 참조 자체는 새로운 사실의 근거가 아니다. 새 주장은 별도 현재 사업 근거 패킷에서 확인한다.'
            )
            # These repeat the check findings and official rubric already below.
            question.pop('positive_evidence', None)
            question.pop('levels', None)
            trace = question.get('scoring_trace') or {}
            trace.pop('levels', None)
    return result
