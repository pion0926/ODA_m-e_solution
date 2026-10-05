"""Move oversized plain-text cells to explicitly paginated, lossless details."""
from html import escape, unescape
import re

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans, get_hwpx_xml_scope_text, set_hwpx_table_cell_text_xml,
)


def fit_table_details(table, overflowing_cells, label):
    """Keep grid/merged cells intact; relocate the largest offending cell first.

    The callback measures the actual layout after every change. Each cell is
    moved at most once, so retries are bounded by the number of cells.
    """
    details = []
    moved = set()
    while True:
        candidates = set(overflowing_cells(table)) - moved
        if not candidates:
            if overflowing_cells(table):
                raise ValueError(f'{label}: 빈 표 구조가 인쇄 영역보다 큽니다.')
            break
        cells = [table[a:b] for a, b in find_hwpx_tag_spans(table, 'hp:tc')]
        index = max(candidates, key=lambda i: len(get_hwpx_xml_scope_text(cells[i])))
        cell = cells[index]
        # These report slots contain text. Never silently discard embedded media.
        if any(tag in cell for tag in ('<hp:pic', '<hp:tbl', '<hp:ole', '<hp:equation')):
            raise ValueError(f'{label}: 큰 셀의 비텍스트 개체를 안전하게 분리할 수 없습니다.')
        paragraphs = [unescape(get_hwpx_xml_scope_text(re.sub(r'<hp:lineBreak\s*/>', '\n', cell[a:b])))
                      for a, b in find_hwpx_tag_spans(cell, 'hp:p')]
        text = '\n'.join(paragraphs)
        code = {'성과지표': 'S', '사업개요': 'O', 'PDM': 'P', '평가매트릭스': 'M', '환류과제': 'R', '교훈': 'L', '평가등급': 'G'}.get(label, 'D') + str(len(details) + 1)
        reference = f'{label} 상세 {code}'
        # Preserve a useful identifying prefix; the complete content follows.
        preview = re.sub(r'\s+', ' ', text).strip()[:16 if label == '평가매트릭스' else 36]
        table, changed = set_hwpx_table_cell_text_xml(table, index, preview + '\n[' + code + ' 상세]', preserve_line_breaks=True)
        if not changed:
            raise ValueError(f'{label}: 상세 본문 연결 실패')
        # The setter retains empty legacy paragraphs. Remove them so their
        # spacing cannot keep an otherwise short reference cell oversized.
        spans = find_hwpx_tag_spans(table, 'hp:tc')
        a, b = spans[index]
        compact = table[a:b]
        ps = find_hwpx_tag_spans(compact, 'hp:p')
        for p, q in reversed(ps[1:]):
            if not get_hwpx_xml_scope_text(compact[p:q]).strip():
                compact = compact[:p] + compact[q:]
        table = table[:a] + compact + table[b:]
        details.append((reference, text))
        moved.add(index)
    return table, details


def append_table_details(table, details):
    """Return a run-compatible fragment with details outside the table.

    Explicit page boundaries also work in readers that do not paginate an
    oversized table cell. Short lines bound even unbroken URLs and newlines.
    No summarization, truncation, or font reduction is involved.
    """
    if not details:
        return table
    paragraphs = []
    used_lines = 0
    page_lines = 24
    for reference, text in details:
        code = reference.rsplit(' ', 1)[-1]
        paragraphs.append(f'<!--odame-detail:{escape(code)}:start--><!--odame-detail-style:2-->')
        # Preserve all characters, including whitespace and Unicode. The page
        # budget belongs to the whole detail appendix, not to each short cell.
        # A heading always has room for at least one following source line.
        lines = re.findall(r'[^\n]{1,60}\n?|\n', text)
        assert ''.join(lines) == text
        offset = 0
        while offset < len(lines):
            if used_lines + 2 > page_lines:
                used_lines = 0
            heading = reference + (' (계속)' if offset else '')
            count = min(page_lines - used_lines - 1, len(lines) - offset)
            paragraphs.append(_paragraph(heading, page_break=used_lines == 0, bold=True))
            for line in lines[offset:offset + count]:
                paragraphs.append(_paragraph(line))
            offset += count
            used_lines += count + 1
        paragraphs.append(f'<!--odame-detail:{escape(code)}:end-->')
    return (table + '</hp:run></hp:p>' + ''.join(paragraphs)
            + '<hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="62">')


def oversized_group_cells(table, groups, budget):
    """Inspect measured physical rows, including cells spanning several rows."""
    rows = find_hwpx_tag_spans(table, 'hp:tr')
    cells = find_hwpx_tag_spans(table, 'hp:tc')
    heights = []
    for a, b in rows:
        single, all_heights = [], []
        for c, d in find_hwpx_tag_spans(table[a:b], 'hp:tc'):
            cell = table[a + c:a + d]
            height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
            if height:
                all_heights.append(int(height[1]))
                if 'rowSpan="1"' in cell:
                    single.append(int(height[1]))
        heights.append(min(single or all_heights or [0]))
    result = set()
    for group in groups:
        if not group or max(group) >= len(rows):
            continue  # Partial preview templates are not the full page grid.
        if sum(heights[i] for i in group) > budget:
            for i in group:
                if i == 0:  # Preserve the repeated header.
                    continue
                a, b = rows[i]
                result.update(j for j, (c, d) in enumerate(cells) if a <= c and d <= b)
    return result


def _paragraph(text, page_break=False, bold=False):
    return (f'<hp:p id="2147483648" paraPrIDRef="39" styleIDRef="0" pageBreak="{int(page_break)}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{85 if bold else 92}"><hp:t>{escape(text)}</hp:t></hp:run></hp:p>')


def resolve_detail_text(section, cell_text):
    """Resolve only an explicit cell reference to its own complete detail block."""
    match = re.search(r'\[([A-Z]\d+) 상세\]', cell_text)
    if not match:
        return cell_text
    code = match[1]
    block = re.search(r'<!--odame-detail:' + code + r':start-->(.*?)<!--odame-detail:' + code + r':end-->', section, re.S)
    if not block:
        raise ValueError(f'표 상세 본문 연결 누락: {code}')
    body_style = '92' if '<!--odame-detail-style:2-->' in block[1] else '85'
    return ''.join(get_hwpx_xml_scope_text(block[1][a:b]) for a, b in find_hwpx_tag_spans(block[1], 'hp:p')
                   if f'charPrIDRef="{body_style}"' in block[1][a:b])
