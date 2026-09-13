"""Loss-aware input recovery at the document boundary, never a factual validator.

The generation gate deliberately remains strict.  This module only repairs
serialization of already stored drafts; it never invents missing slot values.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
import json
import re

from backend.oda_me.reports.context import STRUCTURED_SECTION_SCHEMAS, STRUCTURED_SECTION_SLOT_KEYS


MISSING_SLOT_TEXT = "해당 항목의 작성 내용이 없어 추가 확인이 필요함."


@dataclass
class SlotInput:
    slots: dict[str, str] = field(default_factory=dict)
    detected: bool = False
    warnings: list[str] = field(default_factory=list)
    unassigned_values: list[str] = field(default_factory=list)

    def complete(self, keys: list[str]) -> dict[str, str]:
        values = {key: self.slots.get(key) or MISSING_SLOT_TEXT for key in keys}
        if self.unassigned_values and keys:
            # Keep recoverable prose, not technical JSON syntax.  The audit
            # explicitly records the ambiguous mapping for editorial review.
            first = keys[0]
            existing = self.slots.get(first, "")
            values[first] = "\n\n".join(filter(None, [existing, *self.unassigned_values]))
        return values


def _leaf_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(filter(None, (_leaf_text(item) for key, item in value.items() if key not in {"schema", "metadata"})))
    if isinstance(value, (tuple, list)):
        return "\n".join(filter(None, map(_leaf_text, value)))
    return str(value)


def _without_trailing_commas(text: str) -> str:
    """Remove punctuation outside strings only; body text is byte-preserved."""
    result: list[str] = []
    quoted = escaped = False
    for index, char in enumerate(text):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        if char == ',' and text[index + 1:].lstrip().startswith(('}', ']')):
            continue
        result.append(char)
    return "".join(result)


def read_slot_input(part_id: str, value: object) -> SlotInput:
    """Accept canonical/legacy envelopes and recover completed truncated fields.

    Exact known slot identifiers (including the old space-for-underscore
    mutation) determine the mapping.  Unknown-schema content is not silently
    relabelled.  Missing fields get explicit gaps, never neighbouring facts.
    """
    keys = STRUCTURED_SECTION_SLOT_KEYS.get(part_id)
    if not keys:
        return SlotInput()
    result = SlotInput()
    source = str(value or "").strip()
    parsed: object = value if isinstance(value, dict) else None
    canonical_schema = STRUCTURED_SECTION_SCHEMAS.get(part_id)
    aliases = {re.sub(r"[\s_]+", "_", key): key for key in keys}
    if parsed is None:
        source = re.sub(r"^```(?:json|text)?\s*|\s*```$", "", source, flags=re.I).strip()
        if source.startswith('"'):
            try:
                decoded = json.loads(source, strict=False)
                if isinstance(decoded, str):
                    source = decoded.strip()
                    result.warnings.append("이중 인코딩된 구조화 응답을 복원함")
            except (ValueError, RecursionError):
                pass
        # A short explanation surrounding a JSON object is transport noise.
        start = source.find('{')
        if start < 0:
            return result
        result.detected = True
        candidate = source[start:]
        decoder = json.JSONDecoder(strict=False)
        for repaired in (candidate, _without_trailing_commas(candidate)):
            try:
                parsed, _ = decoder.raw_decode(repaired)
                if repaired != candidate:
                    result.warnings.append("구조화 입력의 후행 쉼표를 복원함")
                break
            except (ValueError, RecursionError):
                continue
        if parsed is None and len(candidate) <= 1_000_000:
            try:
                parsed = ast.literal_eval(candidate)
                result.warnings.append("레거시 구조화 입력의 따옴표 형식을 복원함")
            except (ValueError, SyntaxError, RecursionError, MemoryError):
                pass
        if parsed is None:
            # Truncated JSON: retain complete values and an unterminated final
            # string if adding only its closing quote makes it decodable.
            recovered = {}
            for match in re.finditer(r'"([^"\n]+)"\s*:\s*', candidate):
                key = aliases.get(re.sub(r"[\s_]+", "_", match.group(1).strip()))
                if not key:
                    continue
                tail = candidate[match.end():]
                try:
                    item, _ = decoder.raw_decode(tail)
                except (ValueError, RecursionError):
                    try:
                        item = json.loads(tail.rstrip() + '"', strict=False) if tail.startswith('"') else None
                    except (ValueError, RecursionError):
                        item = None
                if item is not None:
                    recovered[key] = item
            parsed = {"slots": recovered}
            result.warnings.append("손상된 구조화 입력에서 복원 가능한 값만 보존함; 미복원 항목은 추가 확인 필요")
    if not isinstance(parsed, dict):
        return result
    result.detected = True
    if "slots" not in parsed:
        for field_name in ("content", "revised_content"):
            nested = parsed.get(field_name)
            # Decode response envelopes, but never recursively parse arbitrary
            # leaf prose or unbounded/referential Python objects.
            if isinstance(nested, str) and len(nested) < len(source):
                recovered = read_slot_input(part_id, nested)
                if recovered.detected:
                    recovered.warnings.insert(0, "응답 포장 필드에서 구조화 본문을 추출함")
                    return recovered
            if isinstance(nested, dict) and isinstance(nested.get("slots"), dict):
                parsed = nested
                result.warnings.append("응답 포장 필드에서 구조화 본문을 추출함")
                break
    schema = parsed.get("schema")
    if schema is not None and re.sub(r"[\s_]+", "_", str(schema)) != canonical_schema:
        result.warnings.append("다른 섹션의 스키마가 입력됨; 본문 값은 별도 확인 대상으로 보존함")
        result.unassigned_values = [_leaf_text(parsed.get("slots", parsed))]
        return result
    payload = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else parsed
    for raw_key, item in payload.items():
        if raw_key in {"schema", "metadata"}:
            continue
        key = aliases.get(re.sub(r"[\s_]+", "_", str(raw_key).strip()))
        text = _leaf_text(item)
        if key:
            if key in result.slots and result.slots[key] != text:
                result.unassigned_values.append(text)
            else:
                result.slots[key] = text
            if key != raw_key:
                result.warnings.append(f"슬롯 식별자 복원: {key}")
            if not isinstance(item, str):
                result.warnings.append(f"비문자열 슬롯을 본문 값으로 정규화함: {key}")
        elif text:
            result.unassigned_values.append(text)
    missing = [key for key in keys if not result.slots.get(key)]
    if missing:
        result.warnings.append(f"미작성 슬롯 {len(missing)}개를 추가 확인 문구로 표시함")
    if result.unassigned_values:
        result.warnings.append("주소를 확정하지 못한 본문 값을 첫 항목에 보존함; 작성자 검토 필요")
    return result
