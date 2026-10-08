"""Semantic lesson records independent of bullet glyphs and table rendering."""
from __future__ import annotations

import re


_FIELDS = {
    "교훈내용": "lesson", "교훈": "lesson", "일반화원칙": "lesson",
    "분야/일반구분": "category", "분야구분": "category", "분야": "category", "구분": "category",
    "이전년도교훈중복여부": "duplicate", "중복여부": "duplicate",
    "m&e체크리스트질문": "checklist", "m&e체크리스트": "checklist",
    "체크리스트질문": "checklist", "체크리스트": "checklist",
}


def parse_lesson_outline(value: object) -> list[dict[str, str]]:
    """A top-level circle/lesson heading starts a record, a dash never does.

    Keep complete body/checklist strings. Missing metadata is explicitly
    unknown, not an invented "new lesson" classification or checklist.
    """
    chunks: list[tuple[str, list[str]]] = []
    title = ""
    lines: list[str] = []
    for raw in str(value or "").replace("\r", "").splitlines():
        line = re.sub(r"^\s*#{1,6}\s*", "", raw).strip().replace("**", "")
        if not line:
            continue
        match = re.match(r"^(?:[ㅇ❍○◦ᄋ]\s+|교훈\s*\d+\s*[.:)]\s*|\d+[.)]\s+)(.+)$", line)
        if match and not re.match(r"^(?:환류과제(?:\s*및\s*교훈)?|교훈(?:\s*\(Lessons\))?)\s*$", match.group(1), re.I):
            if title:
                chunks.append((title, lines))
            title = match.group(1).strip()
            if title.startswith("(") and title.endswith(")"):
                title = title[1:-1]
            lines = []
        elif title:
            lines.append(line)
    if title:
        chunks.append((title, lines))
    result = []
    for title, lines in chunks:
        fields: dict[str, list[str]] = {"lesson": []}
        current = "lesson"
        for line in lines:
            body = re.sub(r"^\s*[-•∙ㆍ·]\s*", "", line)
            field = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.*)$", body)
            name = _FIELDS.get(re.sub(r"\s+", "", field.group(1)).lower()) if field else None
            if name:
                current = name
                fields.setdefault(current, []).append(field.group(2))
            else:
                fields.setdefault(current, []).append(body)
        rendered = {key: "\n".join(items).strip() for key, items in fields.items()}
        content = rendered.get("lesson") or "교훈 본문이 작성되지 않아 추가 확인이 필요함."
        result.append({
            "observation": title,
            "analysis": content,
            "lesson": content,
            "category": rendered.get("category") or "미기재",
            "duplicate": rendered.get("duplicate") or "확인 필요",
            "checklist": rendered.get("checklist") or "체크리스트 질문이 작성되지 않아 추가 확인이 필요함.",
        })
    return result
