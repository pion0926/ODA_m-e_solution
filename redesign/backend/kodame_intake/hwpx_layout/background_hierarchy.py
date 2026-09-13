"""Repair nested generated bullets only inside the project-background block."""
import re
from html import escape

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans, get_hwpx_xml_scope_text,
    apply_hwpx_report_outline_style_xml,
)


def normalize_background_hierarchy_xml(xml: str) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(xml, 'hp:p')
    active = False
    edits = []
    for start, end in spans:
        p = xml[start:end]
        visible = get_hwpx_xml_scope_text(p)
        visible = re.sub(r'<hp:lineBreak\s*/>', ' ', visible)
        text = re.sub(r'\s+', ' ', visible).strip()
        if text == '1. 사업 추진배경':
            active = True
            continue
        if text == '2. 사업개요':
            active = False
        if not active or '<hp:tbl' in p:
            continue
        match = re.match(r'^ㅇ\s*\(([^()]+)\)\s*ㅇ\s*\(([^()]+)\)\s*(.+)$', text)
        if not match:
            continue
        outer, inner, body = match.groups()
        # Keep both distinct heading labels; demote the inner label to a detail.
        same_title = re.sub(r'\s+', '', outer) == re.sub(r'\s+', '', inner)
        detail = ('' if same_title else f'({inner}) ') + re.sub(r'^-\s*', '', body)
        opening = re.match(r'<hp:p\b[^>]*>', p).group()
        title_p = opening + '<hp:run charPrIDRef="18"><hp:t>' + escape(f'ㅇ ({outer})') + '</hp:t></hp:run></hp:p>'
        detail_opening = re.sub(r'\bid="\d+"', f'id="{3100000000 + start}"', opening, count=1)
        detail_p = detail_opening + '<hp:run charPrIDRef="28"><hp:t>' + escape('- ' + detail) + '</hp:t></hp:run></hp:p>'
        detail_p = apply_hwpx_report_outline_style_xml(detail_p, 'detail')
        edits.append((start, end, title_p + detail_p))
    for start, end, replacement in reversed(edits):
        xml = xml[:start] + replacement + xml[end:]
    return xml, len(edits)
