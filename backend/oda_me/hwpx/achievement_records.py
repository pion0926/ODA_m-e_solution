"""Parse explicit one-line PDM records without absorbing narrative bullets."""
import re

ACHIEVEMENT_RECORD_RE = re.compile(
    r'^\s*-\s*\[((?:outcome|outputs?)(?:\s+|-)[\w.-]+|\d+(?:[.-]\d+)+)(?:\s+[^\]\r\n]+)?\]\s*[:：]?\s*(.*)$',
    re.IGNORECASE,
)

_FIELD_LABELS = r"성과지표|기초선|목표치|종료선 또는 현재 실적|종료선|실적|대비 결과|달성률|달성도|지표입증수단\s*\(MOV\)|지표입증수단|검증수단|비고"


def indexed_record_fields(item: str) -> dict[str, str] | None:
    """Read the explicit field lines produced by ``indexed_achievement_records``.

    Semicolons and labels inside a note describe the measurement selection;
    they are not boundaries between table cells. Legacy free-form records keep
    their existing parser rather than guessing a new field structure.
    """
    lines = item.splitlines()
    if not lines or not re.match(r"^\s*지표\s*ID\s*[:：]", lines[0]):
        return None
    fields, current = {}, None
    for line in lines[1:]:
        if current == '비고':
            fields[current] += "\n" + line
            continue
        match = re.match(rf"^\s*({_FIELD_LABELS})\s*[:：]\s*(.*)$", line)
        if match:
            current = re.sub(r"\s+", "", match[1])
            if current == '종료선또는현재실적':
                current = '종료선'
            fields[current] = match[2]
        elif line.strip():
            # Normalized legacy tables also start with an ID, but may keep
            # aliases such as "실적 (현재시점)". Do not partially interpret
            # those rows as canonical fields or append an alias to a value.
            return None
    return fields if '성과지표' in fields else None


def indexed_achievement_records(body: object) -> list[str]:
    records = []
    for line in str(body or '').splitlines():
        match = ACHIEVEMENT_RECORD_RE.match(line)
        if not match:
            continue
        prefix, *note = re.split(r'\s+/\s+비고\s*[:：]\s*', match[2], maxsplit=1)
        fields = re.split(rf'\s+/\s+(?=(?:{_FIELD_LABELS})\s*[:：])', prefix)
        if note:
            fields.append('비고: ' + note[0])
        first = re.search(r'성과지표\s*[:：]\s*(.*)', fields[0])
        if not first:
            raise ValueError(f'성과지표 레코드에 지표명 필드 누락: {match[1]}')
        fields[0] = '성과지표: ' + first[1]
        fields = [re.sub(r'^종료선 또는 현재 실적\s*[:：]', '종료선:', field) for field in fields]
        records.append('\n'.join(['지표 ID: '+match[1], *fields]))
    return records
