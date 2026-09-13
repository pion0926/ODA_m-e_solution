"""Translate the LLM response envelope without changing section slot contracts."""
from __future__ import annotations

import json
from backend.oda_me.reports.context import STRUCTURED_SECTION_SCHEMAS, STRUCTURED_SECTION_SLOT_KEYS


def section_response_content(payload: dict, part_id: str, field: str = "content") -> str:
    value = payload.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    candidate = value if isinstance(value, dict) else payload
    expected = STRUCTURED_SECTION_SCHEMAS.get(part_id)
    if not expected or not isinstance(candidate.get("slots"), dict):
        return ""
    if candidate.get("schema") not in (None, expected):
        raise ValueError(f"{part_id}: 다른 섹션의 응답 schema입니다.")
    slots = candidate["slots"]
    required = STRUCTURED_SECTION_SLOT_KEYS.get(part_id, ())
    missing = [key for key in required if key not in slots]
    if missing:
        raise ValueError(f"{part_id}: 응답 필수 슬롯 누락: {', '.join(missing)}")
    if not any(isinstance(v, str) and v.strip() for v in slots.values()):
        return ""
    return json.dumps({"schema": expected, "slots": slots}, ensure_ascii=False, indent=2)
def normalize_achievement_structure(content: str) -> str:
    """Give the post-indicator analysis its required heading without rewriting it."""
    import re
    from backend.oda_me.hwpx.achievement_records import ACHIEVEMENT_RECORD_RE
    if re.search(r"(?m)^\s*(?:#{1,6}\s*)?3\.\s*종합\s*평가\s*및\s*시사점", content):
        return content
    lines = content.splitlines()
    record_indexes = [i for i, line in enumerate(lines) if ACHIEVEMENT_RECORD_RE.match(line)]
    if not record_indexes:
        return content
    for i in range(record_indexes[-1] + 1, len(lines)):
        if re.match(r"\s*ㅇ\s+", lines[i]):
            lines[i:i] = ["3. 종합 평가 및 시사점", ""]
            return "\n".join(lines)
    return content
