"""Readable activity labels without changing source numbering or facts."""
import re


def reflow_cell_text(text: str) -> str:
    """Discard PDF-width soft wraps, retaining numbered/bulleted paragraphs."""
    lines: list[str] = []
    for line in str(text).splitlines():
        line = line.strip()
        boundary = re.match(r'^(?:\d+(?:[.-]\d+)*[.)-]?\s|[-•▪▣○●])', line)
        if lines and lines[-1] and line and not boundary:
            lines[-1] += ' ' + line
        else:
            lines.append(line)
    return '\n'.join(lines)


def activity_display_text(text: str) -> str:

    def label(match):
        outer, inner = match.group(1), match.group(2)
        if outer.rstrip('.') == inner.rstrip('.'):
            return outer + ' '
        # The source itself can contain conflicting labels. Do not silently
        # renumber a project activity; make that source discrepancy explicit.
        return outer + ' [원문 활동번호: ' + inner.rstrip('.') + '] '

    return re.sub(r'(?m)^(\d+(?:\.\d+)+\.?)\s*활동\s*\(([^)]+)\)\s*:\s*', label, reflow_cell_text(text))
