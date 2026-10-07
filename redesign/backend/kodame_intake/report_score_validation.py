"""Reject invented current scores when the stored DAC judgment is held.

Historical assessments and rubric descriptions may legitimately contain numbers.
They do not authorize a current score, so exemptions are local to each claim.
"""
import json
import re


CRITERIA = {'relevance':'적절성','coherence':'일관성','effectiveness':'효과성',
            'efficiency':'효율성','sustainability':'지속가능성'}
NUMBER = r'\d+(?:\.\d+)?'
RELATION = r'\s*(?:(?:은|는|이|가|:|：|을|를|으로|로)\s*)?'
TOTAL = re.compile(rf'{NUMBER}\s*/\s*20\s*점?|(?:종합\s*(?:평가\s*)?점수|총점|5대?\s*기준\s*합계){RELATION}{NUMBER}\s*점')
GRADE = re.compile(r'(?:KOICA|코이카)\s*(?:참고\s*)?(?:평가\s*)?(?:등급\s*)?(?:은|는|:|：)?\s*[A-F](?:\s*등급|(?=\s|[,.;]|$))'
                   r'|(?:국무조정실|정부)\s*(?:평가\s*)?(?:등급\s*)?(?:은|는|:|：)?\s*(?:(?:매우|부분)\s*)?(?:성공적|성공|우수|양호|보통|미흡|실패)'
                   r'|종합\s*(?:평가\s*)?등급\s*(?:은|는|:|：)?\s*(?:[A-F](?=등급|\s|[,.;]|$)|(?:(?:매우|부분)\s*)?(?:성공적|성공|우수|양호|보통|미흡|실패))',re.I)
REFERENCE = re.compile(r'과거|이전|종전|당시|기존\s*평가|\d{4}년\s*(?:평가|자체평가)|참고\s*(?:문헌|사례)|예시|등급표|루브릭|배점|채점\s*기준|점수\s*기준|기준상')
CURRENT = re.compile(r'현재|이번|금회|본\s*(?:평가|사업의?\s*평가)|최종\s*평가')
NEGATION = re.compile(r'^\s*(?:(?:으로|로|라고|을|를|이라는|이라고)(?:는)?\s*)?(?:임의(?:로)?\s*)?'
                      r'(?:확정|산정|산출|표기|기재|판정|대체|계산|적용)(?:할\s*수\s*없|하지\s*(?:않|말|못)|해서는\s*안)')


def _reference_claim(segment, start, end):
    before, after = segment[max(0,start-100):start], segment[end:end+100]
    reference = list(REFERENCE.finditer(before))
    current = list(CURRENT.finditer(before))
    if reference and (not current or reference[-1].start() > current[-1].start()):
        return True
    if re.match(r'\s*(?:은|는|이란|이라는)\s*(?:과거|이전|종전|예시|루브릭)', after):
        return True
    return bool(NEGATION.search(after))


def held_score_issues(part_id, content, evaluations):
    rows = [row for row in evaluations if row.get('criterion_id') in CRITERIA]
    held = {row['criterion_id'] for row in rows if row.get('score') is None}
    if not held:
        return []
    issues = []
    # Structured grade slots are field-level assertions, not prose examples.
    if part_id == 'grade':
        try:
            slots = json.loads(content).get('slots', {})
        except (ValueError, AttributeError, TypeError):
            slots = {}
        for key in ('overall_score','koica_grade','government_grade',*(f'{cid}_total_score' for cid in held)):
            value = str(slots.get(key) or '').strip()
            if value and re.search(r'\d|\b[A-F]\b|성공|우수|양호|보통|미흡|실패',value,re.I):
                issues.append(f'저장된 DAC 판정보류와 등급표 {key} 값이 충돌함: {value}. 판정보류로 표시해야 함')
        if slots:
            content = '\n'.join(str(value) for key,value in slots.items() if not key.endswith('_score'))
    for segment in re.split(r'\n|;|(?<!\d)\.(?!\d)|。|(?=하지만|반면|그러나)', str(content or '')):
        for pattern, label in ((TOTAL,'종합점수'),(GRADE,'종합등급')):
            for match in pattern.finditer(segment):
                if not _reference_claim(segment,match.start(),match.end()):
                    issues.append(f'저장된 DAC 종합점수·등급이 판정보류인데 현재 {label}를 임의 확정함: {match[0]}. 보류 상태와 확인된 개별 기준 점수를 구분해야 함')
        for cid in held:
            name=CRITERIA[cid]
            subjects=[re.escape(name)+r'\s*(?:평가\s*)?(?:(?:종합|평균|전체)\s*)?(?:점수|판정|평가결과|평가)?']
            if part_id == 'criteria-'+cid:
                subjects.append(r'(?:종합\s*(?:평가\s*)?점수|종합\s*평가|평균\s*점수|해당\s*기준\s*점수|평가\s*점수)')
            pattern=re.compile(rf'(?:{"|".join(subjects)}){RELATION}({NUMBER})\s*(?:/\s*4\s*)?점')
            for match in pattern.finditer(segment):
                if not _reference_claim(segment,match.start(),match.end()):
                    issues.append(f'저장된 {name} 기준은 판정보류인데 현재 기준 점수를 임의 확정함: {match[0]}. 하위 질문 점수와 기준 판정보류를 구분해야 함')
    return list(dict.fromkeys(issues))
