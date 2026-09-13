"""Bounded, evidence-grounded expansion; never fill length with canned prose."""
from __future__ import annotations

import json
import re
from backend.oda_me.hwpx.adapters.summary_ko import SUMMARY_KO_BLOCKS, validate_summary_ko_payload
from report_outline import nominalize_report_sentences


def expand_short_section(part_id, content, minimum, context, call_json, few_shots):
    if part_id == "summary-ko":
        blocks = [(b.heading, b.min_chars, b.max_chars, b.min_detail_paragraphs, b.required_labels) for b in SUMMARY_KO_BLOCKS]
        sections = re.split(r"(?m)^\s*\([1-5]\)\s+[^\n]+\n", content)
        if len(sections) != 6:
            return content  # structural repair owns malformed block boundaries
        bodies = sections[1:]
    elif len(content) < minimum:
        matches = list(re.finditer(r"(?m)^\s*ㅇ\s+([^\n]+)", content))
        if not matches:
            return content
        blocks = [(m.group(1).strip(), (minimum + len(matches) - 1) // len(matches), minimum * 2, 4, (m.group(1).strip(),)) for m in matches]
        bodies = [content[m.start():matches[i+1].start() if i+1 < len(matches) else len(content)] for i,m in enumerate(matches)]
    else:
        return content
    output = []
    for block_index, ((heading, target, maximum, paragraphs, labels), body) in enumerate(zip(blocks, bodies)):
        for attempt in range(3):
            block_issues = []
            if part_id == 'summary-ko':
                body = '\n'.join(nominalize_report_sentences(line) for line in body.splitlines())
                key = SUMMARY_KO_BLOCKS[block_index].key
                validation = validate_summary_ko_payload({key: body})
                block_issues = [error for error in validation.errors if error.startswith(key + ':')]
            count = len(re.findall(r'(?m)^\s*-\s+', body))
            if target + 80 <= len(body.strip()) <= maximum and count >= paragraphs and not block_issues:
                break
            prompt = f"""현재 보고서의 한 하위 항목만 보완한다. 예시는 형식만 참고하며 예시의 사실은 쓰지 않는다.
[대상 항목] {heading}
[현재 항목] {body}
[이 항목의 실제 검증 실패] {json.dumps(block_issues, ensure_ascii=False)}
[현재 사업 검증 자료] {json.dumps(context, ensure_ascii=False, default=str)}
[필수 구성]
- 이 항목만 {int(target * 1.3)}~{min(maximum, int(target * 1.65))}자로 작성한다. 전체 보고서를 다시 요약하지 않는다.
- 현재 항목은 {len(body.strip())}자, - 문단은 {count}개임. 이 실제 측정값을 기준으로 부족하면 상세화하고, {maximum}자를 초과하면 사실을 보존하며 중복 표현을 정리한다.
- 상위 논점: {', '.join(labels)}. 각 논점은 ㅇ로 시작한다.
- 최소 {paragraphs}개 - 문단을 사용하되, 한 논거의 근거·해석·한계·후속 확인 방법은 2~4문장으로 연결한다.
- 각 ㅇ 논점마다 - 문단을 최소 {(paragraphs + len(labels) - 1) // len(labels) + 1}개씩 작성한다. 각 - 문단은 서로 다른 논거를 120~180자로 설명한다. 상위 논점당 한 문단만 작성하면 검증 실패이므로 반드시 논거를 구분한다.
- 본문 부족 부분은 현재 자료가 의미하는 바와 검증 한계, 확인 절차를 구체화한다. 새 수치·실적·기관·조사를 만들어내거나 같은 말을 반복하지 않는다.
- 문단은 ~함·~음·~됨으로 종결한다. 괄호형 소제목은 필요할 때만 사용한다. 문서명·쪽수 괄호 인용은 넣지 않는다.
- 위 항목 제목 자체는 출력하지 않는다. 지정한 ㅇ 논점과 - 본문만 출력한다.
{{"content":"보완한 해당 항목 본문 전체"}}
JSON만 반환한다."""
            result = call_json("근거 자료만 사용하는 평가보고서 하위 항목 작성자다.", prompt, "KODAME Section Block Expansion", 0.06, few_shot_messages=few_shots)
            candidate = result.get('content')
            if isinstance(candidate, str) and candidate.strip():
                body = candidate.strip()
        output.append((heading + '\n' if part_id == 'summary-ko' else '') + body.strip())
    return '\n\n'.join(output)
