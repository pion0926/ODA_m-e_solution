"""Recompute supported quantitative observations instead of trusting generated ratios."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

class UngroundedNumber(ValueError):
    pass


def number(value):
    if type(value) not in (str,int,float) or isinstance(value,bool):
        raise ValueError('측정값은 유한한 숫자여야 합니다.')
    try:
        result = Decimal(str(value).replace(',',''))
    except InvalidOperation as exc:
        raise ValueError('측정값이 숫자가 아닙니다.') from exc
    if not result.is_finite():
        raise ValueError('측정값은 유한한 숫자여야 합니다.')
    return result


def grounded_number(value, sources):
    expected = number(value)
    tokens = re.findall(r'(?<![\d.,])-?\d[\d,]*(?:\.\d+)?', ' '.join(s['quote'] for s in sources))
    candidates=[number(t) for t in tokens]
    if expected in candidates:
        return expected
    precision=-expected.as_tuple().exponent
    if precision>0:
        quantum=Decimal(10)**-precision
        rounded_candidates={v for v in candidates if v.quantize(quantum,rounding=ROUND_HALF_UP)==expected}
        if len(rounded_candidates)==1:
            return rounded_candidates.pop()  # Compute with the exact source value, never the rounded proposal.
    raise UngroundedNumber(f'측정값 {value}를 지정한 원문에서 확인할 수 없습니다.')


def calculate(measurements, evidence, qid, source_lookup):
    if not isinstance(measurements,list):
        raise ValueError('measurements는 배열이어야 합니다.')
    result = []
    for m in measurements:
        if not isinstance(m,dict) or any(not str(m.get(k) or '').strip() for k in ('metric','unit','period','population')):
            raise ValueError('정량 비교에는 지표·단위·기간·대상이 필요합니다.')
        target_sources=source_lookup(m.get('target_evidence_ids',[]),evidence,qid)
        actual_sources=source_lookup(m.get('actual_evidence_ids',[]),evidence,qid)
        try:
            target = grounded_number(m.get('target'),target_sources)
            actual = grounded_number(m.get('actual'),actual_sources)
        except UngroundedNumber as exc:
            result.append({**m,'ratio':None,'state':'unverified','validation_error':str(exc)})
            continue
        m={**m,'target':float(target),'actual':float(actual)}
        if target <= 0 or actual < 0:
            raise ValueError('목표는 양수, 실적은 0 이상이어야 합니다.')
        direction = m.get('direction')
        if direction not in ('higher','lower','budget','duration') or type(m.get('comparable')) is not bool or type(m.get('due')) is not bool:
            raise ValueError('지표 방향·비교 가능·목표시점 도래 여부를 명시해야 합니다.')
        if not m['comparable'] or not m['due']:
            result.append({**m,'ratio':None,'state':'unverified'})
            continue
        ratio = actual / target if direction != 'lower' else (target / actual if actual else Decimal('1.2'))
        if direction in ('higher','lower'):
            ratio = min(ratio,Decimal('1.2'))
            state = 'verified' if ratio >= 1 else 'substantial' if ratio >= Decimal('.75') else 'limited' if ratio >= Decimal('.5') else 'negative'
        else:
            reason = m.get('justification')
            if reason not in ('verified','asserted','none'):
                raise ValueError('예산·기간 편차의 승인·불가피성 판정이 필요합니다.')
            if reason != 'none' and not source_lookup(m.get('justification_evidence_ids',[]),evidence,qid):
                raise ValueError('편차 사유에는 별도 원문 근거가 필요합니다.')
            state = ('verified' if ratio <= 1 else
                     {'verified':'verified','asserted':'substantial','none':'limited'}[reason] if ratio <= Decimal('1.2') else
                     {'verified':'substantial','asserted':'limited','none':'negative'}[reason] if ratio < Decimal('1.5') else
                     'limited' if reason == 'verified' else 'negative')
        result.append({**m,'ratio':float(ratio),'state':state})
    return result
