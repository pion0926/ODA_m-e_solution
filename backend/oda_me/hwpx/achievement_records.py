"""Parse explicit one-line PDM records without absorbing narrative bullets."""
import re

ACHIEVEMENT_RECORD_RE = re.compile(
    r'^\s*-\s*\[((?:outcome|outputs?)(?:\s+|-)[\w.-]+|\d+(?:[.-]\d+)+)(?:\s+[^\]\r\n]+)?\]\s*[:：]?\s*(.*)$',
    re.IGNORECASE,
)


def indexed_achievement_records(body: object) -> list[str]:
    records = []
    labels = r"성과지표|기초선|목표치|종료선 또는 현재 실적|종료선|실적|대비 결과|달성률|달성도|지표입증수단\s*\(MOV\)|지표입증수단|검증수단|비고"
    for line in str(body or '').splitlines():
        match = ACHIEVEMENT_RECORD_RE.match(line)
        if not match:
            continue
        fields = re.split(rf'\s+/\s+(?=(?:{labels})\s*[:：])', match[2])
        first = re.search(r'성과지표\s*[:：]\s*(.*)', fields[0])
        if not first:
            raise ValueError(f'성과지표 레코드에 지표명 필드 누락: {match[1]}')
        fields[0] = '성과지표: ' + first[1]
        fields = [re.sub(r'^종료선 또는 현재 실적\s*[:：]', '종료선:', field) for field in fields]
        records.append('\n'.join(['지표 ID: '+match[1], *fields]))
    return records
