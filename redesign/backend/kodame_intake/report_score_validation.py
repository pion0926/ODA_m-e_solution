"""Reject invented current scores when the stored DAC judgment is held.

Historical assessments and rubric descriptions may legitimately contain numbers.
They do not authorize a current score, so exemptions are local to each claim.
"""
import json
import re
from decimal import Decimal, InvalidOperation


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


def _known_criterion_total_claim(segment, match, rows):
    """An explicitly named, saved criterion score is not the five-criterion sum."""
    score = re.fullmatch(rf'종합\s*(?:평가\s*)?점수{RELATION}({NUMBER})\s*점', match[0])
    if score is None:
        return False
    before = segment[:match.start()]
    subject = re.search(r'(?<![가-힣])(' + '|'.join(CRITERIA.values()) + r')(?:\s*기준)?(?:의)?\s*$', before)
    if subject is None:
        return False
    # A criterion name does not authorize reframing its number as an overall
    # score. Delimiters keep an unrelated later held-total notice independent.
    after = re.split(r'[,，;]', segment[match.end():], maxsplit=1)[0]
    overall_scope = r'전체|총점|(?:5|다섯)\s*(?:대\s*)?(?:평가\s*)?기준|20\s*점'
    if re.search(overall_scope, before) or re.search(overall_scope, after):
        return False
    saved = next((row.get('score') for row in rows if CRITERIA.get(row['criterion_id']) == subject[1]), None)
    if saved is None:
        return False
    try:
        return Decimal(score[1]) == Decimal(str(saved))
    except (InvalidOperation, ValueError):
        return False


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
                if pattern is TOTAL and _known_criterion_total_claim(segment, match, rows):
                    continue
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


def observed_score_issues(part_id, content, evaluations):
    """A source-confidence caveat must not erase a saved performance score.

    Match explicit criterion/overall score assertions only. Missing individual
    questions, historical decisions and ordinary evidence caveats are distinct.
    """
    rows = {row['criterion_id']: row for row in evaluations
            if row.get('criterion_id') in CRITERIA}
    known = {cid: row['score'] for cid, row in rows.items() if row.get('score') is not None}
    if not known:
        return []
    overall_known = set(known) == set(CRITERIA)
    held = r'(?:판정\s*)?보류'
    issues = []
    if part_id == 'grade':
        try:
            slots = json.loads(content).get('slots', {})
        except (ValueError, AttributeError, TypeError):
            slots = {}
        if isinstance(slots, dict):
            keys = [f'{cid}_total_score' for cid in known]
            if overall_known:
                keys += ['overall_score', 'koica_grade', 'government_grade']
            for key in keys:
                if re.search(held, str(slots.get(key) or '')):
                    issues.append(f'저장된 성과 점수가 있는데 등급표 {key}를 보류로 바꿈. 저장 점수를 유지하고 증빙 보완사항을 별도로 설명해야 함')
            if slots:
                content = '\n'.join(str(value) for key, value in slots.items()
                                    if not key.endswith('_score'))
    subjects = [re.escape(CRITERIA[cid]) + r'(?:\s*기준)?(?:의)?\s*'
                r'(?:(?:종합|평균|전체)\s*)?(?:평가\s*)?(?:점수|판정|평가결과)?'
                for cid in known]
    if part_id.removeprefix('criteria-') in known:
        subjects += [r'(?:해당\s*기준\s*점수|기준\s*점수|평균\s*점수|평가\s*점수)']
    if overall_known:
        subjects += [r'(?:종합\s*(?:평가\s*)?(?:점수|등급|판정)|총점|전체\s*평가\s*점수)']
    qualifications = r'(?:(?:현재|이번|아직|(?:증빙|자료|근거)\s*부족으로|(?:증빙|자료|근거)가\s*부족하여)\s*)*'
    pattern = re.compile(r'(?<![가-힣])(?:' + '|'.join(subjects) + r')' + RELATION + qualifications + held)
    denied = re.compile(r'^\s*(?:(?:로|라고|라는|가|는)(?:는)?\s*)?'
                        r'(?:아니|하지\s*(?:않|말)|처리하지|바꾸지|전환하지)')
    for segment in re.split(r'\n|;|(?<!\d)\.(?!\d)|。|(?=하지만|반면|그러나)', str(content or '')):
        for match in pattern.finditer(segment):
            if _reference_claim(segment, match.start(), match.end()) or denied.search(segment[match.end():]):
                continue
            # A generic score phrase can belong to an explicitly scoped child
            # question even when the enclosing criterion has a saved score.
            before = re.split(r'[,，;]', segment[:match.start()])[-1]
            generic_question_score = re.match(r'(?:평균|평가)\s*점수', match[0])
            if generic_question_score and re.search(r'질문|문항|\bq\d+\b', before, re.I):
                continue
            issues.append(f'저장된 성과 점수를 현재 판정보류로 바꿈: {match[0]}. 확인된 점수는 유지하고 증빙 부족·신뢰도는 별도로 설명해야 함')
    return list(dict.fromkeys(issues))
