from __future__ import annotations

import html
import itertools
import re


_DANGLING_CONNECTORS = {"및", "과", "와", "·", "and", "or"}


def _visual_width(value: str) -> float:
    """Approximate a centered HWP title line in Korean-character units."""

    width = 0.0
    for char in value:
        if char.isspace():
            width += 0.35
        elif "\uac00" <= char <= "\ud7a3" or "\u3131" <= char <= "\u318e":
            width += 1.0
        elif char.isalnum():
            width += 0.58
        else:
            width += 0.4
    return width


def cover_title_font_height(title: object) -> int:
    """Return a print-safe cover title size in 1/100 pt units."""

    compact = re.sub(r"\s+", "", str(title or ""))
    if len(compact) > 52:
        return 2600
    if len(compact) > 38:
        return 2800
    if len(compact) > 30:
        return 3000
    if len(compact) > 24:
        return 3400
    if len(compact) > 18:
        return 4000
    return 4800


def adapt_cover_title_font_xml(xml: str, project: dict) -> tuple[str, int]:
    """Scale only the template's cover title character property."""

    height = cover_title_font_height(project.get("title"))
    pattern = re.compile(r'(<hh:charPr\b[^>]*\bid="58"[^>]*\bheight=")\d+("[^>]*>)')
    adapted, count = pattern.subn(lambda match: f"{match.group(1)}{height}{match.group(2)}", xml, count=1)
    if count != 1:
        raise RuntimeError("표지 제목 글자속성(charPr 58)을 찾지 못했습니다.")
    return adapted, height


def split_cover_title(title: str, max_width: float = 19.5) -> list[str]:
    """Balance a long title without leaving a connector on its own line."""

    tokens = re.sub(r"\s+", " ", str(title or "")).strip().split(" ")
    words: list[str] = []
    for token in tokens:
        if token:
            words.append(token)

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        connector = word.casefold() in _DANGLING_CONNECTORS
        if current and _visual_width(candidate) > max_width and not connector:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    # Greedy wrapping prevents overflow but can leave a visually weak final
    # line such as a single noun. Keep the same line count and choose the
    # lowest-variance legal partition so the centered cover reads as one
    # title block. Titles are short, so exhaustive boundary scoring is both
    # deterministic and easier to audit than layout-specific heuristics.
    line_count = min(len(lines), 4)
    if 1 < line_count <= len(words):
        target_width = _visual_width(" ".join(words)) / line_count
        best: tuple[float, list[str]] | None = None
        for boundaries in itertools.combinations(range(1, len(words)), line_count - 1):
            starts = (0, *boundaries)
            ends = (*boundaries, len(words))
            candidate_lines = [" ".join(words[start:end]) for start, end in zip(starts, ends)]
            widths = [_visual_width(line) for line in candidate_lines]
            if any(width > max_width for width in widths):
                continue
            if any(line.split(" ")[0].casefold() in _DANGLING_CONNECTORS for line in candidate_lines):
                continue
            if any(line.split(" ")[-1].casefold() in _DANGLING_CONNECTORS for line in candidate_lines[:-1]):
                continue
            score = sum((width - target_width) ** 2 for width in widths)
            if any(len(line.split(" ")) == 1 for line in candidate_lines):
                score += max_width**2
            if best is None or score < best[0]:
                best = (score, candidate_lines)
        if best is not None:
            lines = best[1]

    # A connector must stay with the phrase before it even if a future title
    # happens to arrive already split into unusual whitespace tokens.
    for index in range(1, len(lines)):
        first_word, *rest = lines[index].split(" ")
        if first_word.casefold() not in _DANGLING_CONNECTORS:
            continue
        lines[index - 1] = f"{lines[index - 1]} {first_word}".strip()
        lines[index] = " ".join(rest).strip()
    lines = [line for line in lines if line]

    return lines


def wrap_cover_title_xml(xml: str, project: dict) -> tuple[str, int]:
    title = re.sub(r"\s+", " ", str(project.get("title") or "")).strip()
    lines = split_cover_title(title)
    if len(lines) < 2:
        return xml, 0
    escaped_title = html.escape(title, quote=False)
    replacement = "<hp:lineBreak/>".join(html.escape(line, quote=False) for line in lines)
    pattern = re.compile(rf"(<hp:t\b[^>]*>){re.escape(escaped_title)}\s*(</hp:t>)")
    return pattern.subn(lambda match: match.group(1) + replacement + match.group(2), xml, count=1)
