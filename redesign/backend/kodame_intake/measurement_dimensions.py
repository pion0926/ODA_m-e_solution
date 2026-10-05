"""Do not compare a formula score or percentage with a counted quantity."""
import re

UNITS = r'%|명|건|회|종|권|개'


def validate_dimension(indicator, observation):
    from .pdm_evidence import _number
    text = str(indicator.get('indicator') or indicator.get('text') or '')
    expected = set(re.findall(r'\(\s*(' + UNITS + r')\s*\)', text))
    if not expected and re.search(r'률|비율|비중', text):
        expected = {'%'}
    numeric = _number(observation.get('value'))
    if re.search(r'\(\s*유\s*/\s*무\s*\)', text):
        if numeric:
            return None, '승인 여부를 달성률·진척도 숫자로 대체하지 않습니다.'
        label = str(observation.get('value') or '').strip()
        if label == '완료' and '승인' in str(observation.get('quote') or ''):
            return {**observation, 'value': '유'}, None
        if label in {'승인', '승인 완료', '승인 유지', '유(승인)', '유'}:
            return {**observation, 'value': '유'}, None
        if label in {'미승인', '승인 없음', '무'}:
            return {**observation, 'value': '무'}, None
    if not numeric or not expected:
        return observation, None
    number, unit = numeric
    quote = str(observation.get('quote') or '')
    explicit = {u for n, u in re.findall(r'(?<![\d.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(' + UNITS + r')', quote)
                if float(n.replace(',', '')) == number}
    if not unit:
        matching = explicit & expected
        if len(matching) == 1:
            unit = next(iter(matching))
            observation = {**observation, 'value': f'{number:g}{unit}'}
        else:
            return None, '지표의 측정단위를 확인할 수 없는 숫자는 비교하지 않습니다.'
    if unit not in expected:
        return None, '지표의 측정단위와 문서 수치의 단위가 다릅니다.'
    if explicit and unit not in explicit:
        return None, '제안된 단위를 해당 원문 숫자에서 확인할 수 없습니다.'
    if re.search(r'산출식|달성률|달성도|목표\s*대비', quote) and unit != '%' and unit not in explicit:
        return None, '산출식·달성률 숫자를 인원·수량 실적으로 환산하지 않습니다.'
    return observation, None
