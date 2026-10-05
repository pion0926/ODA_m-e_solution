"""AI review is advisory; missing scores are not zero or fabricated scores."""
import math


def score_or_none(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 100 else None
    except (TypeError, ValueError):
        return None


def review_schema():
    def obj(props):
        return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}
    strings = {'type': 'array', 'items': {'type': 'string'}}
    score = {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100}
    return obj({'revised_content': {'type': 'string'}, 'quality_score': score,
        'dimension_scores': obj({k: score for k in ('grounding','analysis','specificity','structure','professional_style','completeness')}),
        'quality_issues': strings, 'evidence_coverage': strings, 'unresolved_evidence_gaps': strings,
        'claim_checks': {'type': 'array', 'items': obj({'claim': {'type': 'string'},
            'evidence_ids': strings, 'counterevidence_ids': strings,
            'verdict': {'type': 'string', 'enum': ['supported','conflicting','deferred']}})}})


def claim_audit(review, evidence):
    allowed = {e.get('id') or e.get('evidence_id') for e in evidence}
    checks = review.get('claim_checks') or []
    issues = []
    for check in checks:
        if any(ref not in allowed for ref in check.get('evidence_ids', []) + check.get('counterevidence_ids', [])):
            issues.append('확인되지 않은 근거 연결: ' + check.get('claim', '')[:150])
        if check.get('verdict') == 'supported' and not check.get('evidence_ids'):
            issues.append('근거 없는 확정 주장: ' + check.get('claim', '')[:150])
    return {'claims': checks, 'issues': issues, 'human_review_required': True}
