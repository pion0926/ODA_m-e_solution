"""Grounded registration facts; navigation aids, never evaluation conclusions."""
import hashlib

VERSION = 'intake-facts-v2'
PROMPT = '''
문서 등록을 위한 사실 목록도 추출한다. 최종 성과 인정·달성도·리스크·DAC 점수는 산정하지 않는다.
document_role에는 등록 사업계획서의 목표·활동과 대조하여 이 문서의 의미, 역할, 활용 가능 범위와 한계를 한국어로 간결히 쓴다.
각 사실은 facts에 따로 기록한다. pdm_indicator_ids는 직접 관련된 PDM 지표만, dac_question_ids는 관련 종료평가 세부질문만 연결한다.
목표·실적·기준값·계획·실행·산출물·제약을 구분하고, 수치뿐 아니라 활동 이행, 수요, 협력, 예산·일정, 효과, 지속가능성의 사실도 추출한다.
긍정적 내용과 부정적 내용·한계를 모두 보존한다. 관련성이 없으면 배열을 비운다.
value, unit, period, population은 원문에 있는 경우만 기록한다. 없으면 빈 문자열이다. N/A를 0으로 바꾸지 않는다.
statement는 하나의 사실만 한국어로 정리하고 evidence_quote는 그 사실을 직접 입증하는 1500자 이하 연속 원문이다.
source_id 선택지가 제공되면 인용문을 다시 쓰지 말고 그 사실이 실제 있는 원문 조각의 source_id를 선택한다. 서버가 원문을 그대로 저장한다. 셀 주소·구분자도 원문 일부이며 바꿔 쓰지 않는다.
주장·계획·보고 실적은 독립 검증된 결과가 아니다. 교재의 사례·타사업 통계를 현재 사업 실적으로 추출하지 않는다.
여러 지표에 쓰이는 동일 사실은 하나로 저장하고 관련 ID를 배열로 연결한다.
'''


def schema(indicators, questions, sources=None):
    string = {'type': 'string'}
    props = {key: string for key in ('statement', 'value', 'unit', 'period', 'population', 'evidence_quote')}
    if sources is not None:
        props.pop('evidence_quote')
        props['source_id'] = {'type': 'string', 'enum': list(sources)}
    props.update(kind={'type':'string','enum':['target','baseline','reported_actual','plan','activity','output','limitation','context']},
                 pdm_indicator_ids={'type':'array','items':{'type':'string','enum':list(indicators)}},
                 dac_question_ids={'type':'array','items':{'type':'string','enum':list(questions)}})
    return {'type':'array','items':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}


def reference_blocks(text):
    """Server-owned exact snippets; keep spreadsheet rows intact."""
    import re
    result, buffer = {}, ''
    def add(value):
        if value:
            result[f'S{len(result)+1:04d}'] = value
    for line in text.splitlines(keepends=True):
        if re.match(r'^[A-Z]+\d+=', line):
            add(buffer)
            buffer = ''
            for start in range(0, len(line), 1200):
                add(line[start:start+1200])
        else:
            if len(buffer) + len(line) > 1200:
                add(buffer)
                buffer = ''
            while len(line) > 1200:
                add(line[:1200])
                line = line[1200:]
            buffer += line
    add(buffer)
    return result


def resolve_source(item, sources):
    if 'source_id' not in item:
        return item  # Legacy JSON-mode response, still requires exact grounding.
    source = sources.get(item['source_id']) if isinstance(item['source_id'], str) else None
    return {**item, 'evidence_quote': source or ''}


def ground_facts(items, chunk, *, start, indicators, questions, artifact=False):
    # Map whitespace-normalized quotes back to exact supplied-text offsets.
    positions = [i for i, ch in enumerate(chunk) if not ch.isspace()]
    compact = ''.join(chunk[i] for i in positions)
    found = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        quote = str(item.get('evidence_quote') or '')
        needle = ''.join(quote.split())
        index = compact.find(needle) if needle and len(quote) <= 1500 else -1
        if index < 0:
            continue
        pdm = [key for key in item.get('pdm_indicator_ids', []) if key in indicators]
        dac = [key for key in item.get('dac_question_ids', []) if key in questions]
        if not (pdm or dac):
            continue
        value = str(item.get('value') or '')
        if value and ''.join(value.split()) not in needle:
            continue
        # Partial books are registered as artifacts, not measured project results.
        if artifact and item.get('kind') in ('reported_actual', 'baseline', 'target'):
            continue
        lo, hi = positions[index], positions[index + len(needle)-1] + 1
        key = hashlib.sha256((needle + str(item.get('kind')) + str(sorted(pdm)) + str(sorted(dac))).encode()).hexdigest()[:24]
        found.append({**item, 'id':key,'pdm_indicator_ids':pdm,'dac_question_ids':dac,
                      'evidence_quote':chunk[lo:hi], 'source_start':start+lo,'source_end':start+hi,
                      'source_coordinates':'redacted_chunk', 'chunk_start':start,
                      'scope':'sample_only' if artifact else 'full_text', 'verification':'source_quote_verified'})
    return found
