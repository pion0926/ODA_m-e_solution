from __future__ import annotations

import re


_INLINE_SOURCE_LOCATION_RE = re.compile(
    r"(?:"
    r"pp?\.\s*\d+(?:\s*[-–~]\s*\d+)?"
    r"|\d+(?:\s*[-–~]\s*\d+)?\s*쪽"
    r"|(?:페이지|쪽)\s*\d+(?:\s*[-–~]\s*\d+)?"
    r"|추출\s*항목\s*\d+"
    r")",
    re.IGNORECASE,
)
_INLINE_SOURCE_DOCUMENT_RE = re.compile(
    r"(?:"
    r"자체평가(?:결과)?보고서|사업계획서|사업기본자료|"
    r"사업설계매트릭스|결과보고서|조사보고서|연차보고서|"
    r"평가보고서|성과보고서|진도보고서"
    r")",
    re.IGNORECASE,
)


def strip_inline_source_citations(value: object) -> str:
    """Remove parenthetical source-location notes while preserving normal parentheses.

    The scanner understands one or more nested parenthetical labels such as
    ``(최신 사업설계매트릭스(PDM), p. 7)``.  Acronyms and explanatory
    parentheses without a page or extraction location remain untouched.
    """

    text = str(value or "")
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for index, char in enumerate(text):
        if char == "(":
            stack.append(index)
            continue
        if char != ")" or not stack:
            continue
        start = stack.pop()
        inner = text[start + 1 : index]
        if not (
            _INLINE_SOURCE_LOCATION_RE.search(inner)
            or _INLINE_SOURCE_DOCUMENT_RE.search(inner)
        ):
            continue
        # Prefer the outer citation group when it closes later.  A matching
        # inner span is discarded if its enclosing group also names a source.
        spans.append((start, index + 1))

    selected: list[tuple[int, int]] = []
    for start, end in sorted(spans, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(parent_start <= start and end <= parent_end for parent_start, parent_end in selected):
            continue
        selected = [
            (child_start, child_end)
            for child_start, child_end in selected
            if not (start <= child_start and child_end <= end)
        ]
        selected.append((start, end))

    for start, end in sorted(selected, reverse=True):
        remove_start = start
        while remove_start > 0 and text[remove_start - 1] in " \t":
            remove_start -= 1
        text = text[:remove_start] + text[end:]

    # Achievement and evidence adapters historically emitted reader-facing
    # location fields.  They are verification metadata, not report prose.
    text = re.sub(
        r"(?m)^[ \t]*[-*•]?[ \t]*근거[ \t]*위치[ \t]*[:：][^\n]*(?:\n|$)",
        "",
        text,
    )
    text = re.sub(r"[ \t]*[·•][ \t]*근거[ \t]*위치[ \t]*[:：][^\n]*", "", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?。、])", r"\1", text)
    text = re.sub(r"([.!?。])\1+", r"\1", text)
    return text.strip()
