"""Prevent inherited template cell squeeze modes from overprinting long text."""
import re
from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans


def normalize_table_cell_wrapping(xml: str) -> tuple[str, int]:
    cells = find_hwpx_tag_spans(xml, 'hp:tc')
    edits = []
    for match in re.finditer(r'<hp:subList\b[^>]*>', xml):
        if not any(start < match.start() < end for start, end in cells):
            continue
        opening = match.group()
        updated = re.sub(r'\blineWrap="[^"]*"', 'lineWrap="BREAK"', opening)
        if 'lineWrap=' not in opening:
            updated = opening[:-1] + ' lineWrap="BREAK">'
        if updated != opening:
            edits.append((match.start(), match.end(), updated))
    for start, end, updated in reversed(edits):
        xml = xml[:start] + updated + xml[end:]
    return xml, len(edits)
