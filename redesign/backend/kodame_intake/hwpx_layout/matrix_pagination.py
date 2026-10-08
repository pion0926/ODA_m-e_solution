"""Keep matrix evidence in repeated-header tables, including oversized rows."""
from html import escape, unescape
import re

from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans, get_hwpx_xml_scope_text


def _text(cell):
    return unescape(get_hwpx_xml_scope_text(re.sub(r'<hp:lineBreak\s*/>', '\n', cell)))


def _cell(cell, text):
    start = re.search(r'<hp:subList\b[^>]*>', cell).end()
    end = cell.index('</hp:subList>')
    paragraph = ('<hp:p id="2147483648" paraPrIDRef="39" styleIDRef="0" '
                 'pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="92"><hp:t>'
                 + escape(text).replace('\n', '<hp:lineBreak/>') + '</hp:t></hp:run></hp:p>')
    return cell[:start] + paragraph + cell[end:]


def paginate_matrix(table, measure, budget, header_height):
    spans = find_hwpx_tag_spans(table, 'hp:tr')
    rows = [table[a:b] for a, b in spans]
    if len(rows) != 9:
        raise ValueError('평가매트릭스는 머리행과 8개 기준 행이 필요합니다.')
    physical = []
    for row in rows[1:]:
        if measure(row) + header_height <= budget:
            physical.append(row)
            continue
        cells = [row[a:b] for a, b in find_hwpx_tag_spans(row, 'hp:tc')]
        if len(cells) != 5 or any(re.search(r'<hp:(?:tbl|pic|ole|equation)\b', cell) for cell in cells):
            raise ValueError('평가매트릭스 행의 비텍스트 내용을 안전하게 분할할 수 없습니다.')
        remaining = [_text(cell) for cell in cells[1:]]
        label, continuation = _text(cells[0]), False
        while any(remaining):
            pieces = []
            for index, text in enumerate(remaining, 1):
                lo, hi = 0, len(text)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    probe = '<hp:tr>' + _cell(cells[index], text[:mid]) + '</hp:tr>'
                    if measure(probe) + header_height <= budget: lo = mid
                    else: hi = mid - 1
                if text and not lo:
                    raise ValueError('평가매트릭스 셀의 한 글자도 인쇄 영역에 배치할 수 없습니다.')
                # Prefer a word boundary, without dropping any characters.
                if lo < len(text):
                    boundary = max(text.rfind('\n', 0, lo), text.rfind(' ', 0, lo))
                    if boundary >= lo // 2: lo = boundary + 1
                pieces.append(_cell(cells[index], text[:lo]))
                remaining[index - 1] = text[lo:]
            physical.append('<hp:tr>' + _cell(cells[0], label + (' (계속)' if continuation else '')) + ''.join(pieces) + '</hp:tr>')
            continuation = True

    groups, current, height = [], [], header_height
    for row in physical:
        needed = measure(row)
        if current and height + needed > budget:
            groups.append(current); current, height = [], header_height
        current.append(row); height += needed
    if current: groups.append(current)
    prefix, suffix = table[:spans[0][0]], table[spans[-1][1]:]
    base_id = int(re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)[1])
    parts = []
    for index, group in enumerate(groups):
        selected, total = [], 0
        for row_index, row in enumerate([rows[0], *group]):
            size = header_height if row_index == 0 else measure(row)
            row = re.sub(r'(<hp:cellAddr\b[^>]*\browAddr=")\d+', rf'\g<1>{row_index}', row)
            row = re.sub(r'(<hp:cellSz\b[^>]*\bheight=")\d+', rf'\g<1>{size}', row)
            selected.append(row); total += size
        opening = re.sub(r'(<hp:tbl\b[^>]*\bid=")\d+', rf'\g<1>{base_id + index}', prefix, count=1)
        opening = re.sub(r'(\browCnt=")\d+', rf'\g<1>{len(selected)}', opening, count=1)
        opening = re.sub(r'(<hp:sz\b[^>]*\bheight=")\d+', rf'\g<1>{total}', opening, count=1)
        parts.append(opening + ''.join(selected) + suffix)
    separator = '</hp:run></hp:p><hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" pageBreak="1" columnBreak="0" merged="0"><hp:run charPrIDRef="62">'
    return separator.join(parts)
