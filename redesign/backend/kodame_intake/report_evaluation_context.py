"""Reuse validated DAC decisions without resending their full raw corpus.

Original quotes and scoring traces remain immutable in criterion_evaluations.
The report has a separate source-evidence packet for new prose claims.
"""
from copy import deepcopy


def for_report(evaluations):
    result = deepcopy(evaluations)
    for criterion in result:
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
