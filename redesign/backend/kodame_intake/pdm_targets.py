"""Recover explicit target values from preserved PDM indicator text.

Only unambiguous dated baseline/target pairs or deadline expressions qualify.
Never infer a target from the largest number or from a measurement's unit label.
"""
import re
from decimal import Decimal, ROUND_HALF_UP

AMOUNT = r'\d[\d,]*(?:\.\d+)?\s*(?:%|명|건|회|종|권|개|동)'
DATED = re.compile(r"(?:['’‘]\s*(\d{2})|(20\d{2}))\s*년?\s*[:：]?\s*(" + AMOUNT + r')(?![\d?？])')
DEADLINE = re.compile(r'(?:까지|목표\s*[:：]|목표치는?|목표값\s*[:：])\s*[^\d\n,;()]{0,16}(' + AMOUNT + r')(?![\d?？])')


def explicit_target(text):
    text = str(text or '')
    dated = list(DATED.finditer(text))
    if len(dated) >= 2:
        years = [int(m[2] or ('20' + m[1])) for m in dated]
        # A single baseline and later endpoint; repeated years indicate submetrics.
        if len(set(years)) != len(years):
            return None
        chosen = dated[years.index(max(years))]
        # Reject mixed dimensions and composite targets rather than choosing one.
        units = {re.search(r'[^\d\s,.]+$', m[3])[0] for m in dated}
        if len(units) != 1 or len(dated) != 2 or re.search(r'n\.?a\.?', text, re.I):
            return None
        return {'value': re.sub(r'\s+', '', chosen[3]), 'quote': text,
                'period': str(max(years)), 'origin': 'pdm_explicit_target'}
    matches = list(DEADLINE.finditer(text))
    if len(matches) == 1:
        # Multiple quantities in a deadline clause need separate submetrics.
        tail = text[matches[0].start():]
        if len(re.findall(AMOUNT, tail)) == 1 and not re.search(r'n\.?a\.?', tail, re.I):
            return {'value': re.sub(r'\s+', '', matches[0][1]), 'quote': text,
                    'period': '', 'origin': 'pdm_explicit_target'}
    return None


def apply_pdm_targets(indicators, source_id):
    changed = set()
    for item in indicators:
        target = explicit_target(item.get('indicator'))
        if not target:
            continue
        if item.get('target') != target['value']:
            changed.add(item['id'])
        item['target'] = target['value']
        item['pdm_target'] = {**target, 'document_id': str(source_id)}
        item['target_review_required'] = False
        item.setdefault('selected_measurements', {})['target'] = {
            **item['pdm_target'], 'kind': 'target', 'indicator_id': item['id']}
        # A reported target does not amend the PDM. Preserve differences for review.
        item['reported_target_differences'] = [o for o in item.get('measurement_sources', [])
            if o.get('kind') == 'target' and re.sub(r'\s+', '', str(o.get('value'))) != target['value']]
        from .pdm_evidence import _number
        expected, actual = _number(target['value']), _number(item.get('actual'))
        item['achievement_rate'] = None
        if (item.get('measurement_status') not in ('incomplete', 'conflict')
                and expected and actual and expected[0] > 0 and expected[1] == actual[1]):
            item['achievement_rate'] = float((Decimal(str(actual[0])) / Decimal(str(expected[0])) * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP))
        rate = item['achievement_rate']
        item['status'] = 'unset' if rate is None else 'ok' if rate >= 100 else 'watch' if rate >= 70 else 'under'
    return changed
