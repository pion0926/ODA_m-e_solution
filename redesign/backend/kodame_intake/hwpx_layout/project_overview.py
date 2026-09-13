from __future__ import annotations

import math
import re

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans,
    find_hwpx_table_span_by_text,
    get_hwpx_xml_scope_text,
    set_hwpx_xml_scope_text,
)

from ..quality_profile import layout_profile


_PROFILE = layout_profile("project_overview")
CANONICAL_HEADING = str(_PROFILE["canonical_heading"])
AUTHORING_NOTES = tuple(str(item) for item in _PROFILE.get("remove_authoring_notes") or ())
TABLE_CELL_MARGIN_VERTICAL = int(_PROFILE.get("table_cell_margin_vertical") or 100)
SOURCE_CELL_MARGIN_VERTICAL = int(_PROFILE.get("source_cell_margin_vertical") or 566)
TABLE_ROW_MIN_HEIGHT = int(_PROFILE.get("table_row_min_height") or 1500)
TABLE_COLUMN_WIDTHS = tuple(_PROFILE.get("column_widths") or (2600, 8500, 7400, 28961))
TABLE_FONT_HEIGHT = int(_PROFILE.get("font_height") or 1000)
TABLE_LINE_HEIGHT = TABLE_FONT_HEIGHT * int(_PROFILE.get("line_spacing_percent") or 130) // 100
TABLE_MARGIN_HORIZONTAL = int(_PROFILE.get("cell_margin_horizontal") or 240)
TABLE_PAGE_BUDGET = int(_PROFILE.get("page_height_budget") or 60000)


def _split_overview_at_merged_groups(table: str) -> str:
    """Inline tables do not reliably paginate in every reader; split explicitly.

    Preserve whole merged groups (overview / contributions) and repeat the
    header. Never shrink text, crop the last row, or break a merged cell.
    """
    spans = find_hwpx_tag_spans(table, "hp:tr")
    if len(spans) < 2:
        return table
    rows = [table[start:end] for start, end in spans]
    heights = [_physical_row_height(row) for row in rows]
    if sum(heights) <= TABLE_PAGE_BUDGET:
        return table
    groups = []
    start = 1
    while start < len(rows):
        end = start + 1
        cursor = start
        while cursor < end:
            counts = [int(value) for value in re.findall(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', rows[cursor])]
            end = max(end, cursor + max(counts or [1]))
            cursor += 1
        if end > len(rows):
            raise ValueError("사업개요 병합 셀의 행 범위가 표를 벗어났습니다.")
        groups.append(list(range(start, end)))
        start = end
    pages, current = [], [0]
    for group in groups:
        if heights[0] + sum(heights[i] for i in group) > TABLE_PAGE_BUDGET:
            raise ValueError("사업개요의 한 병합 그룹이 한 쪽을 초과합니다. 해당 셀의 내용을 보완한 후 다시 생성해 주세요.")
        if sum(heights[i] for i in current + group) > TABLE_PAGE_BUDGET:
            pages.append(current)
            current = [0]
        current.extend(group)
    pages.append(current)
    prefix, suffix = table[:spans[0][0]], table[spans[-1][1]:]
    base_id = int(re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix).group(1))
    pieces = []
    for offset, indexes in enumerate(pages):
        opening = re.sub(r'(<hp:tbl\b[^>]*\bid=")\d+', rf'\g<1>{base_id + offset}', prefix, count=1)
        opening = re.sub(r'(<hp:tbl\b[^>]*\browCnt=")\d+', rf'\g<1>{len(indexes)}', opening, count=1)
        opening = re.sub(r'(<hp:sz\b[^>]*\bheight=")\d+', rf'\g<1>{sum(heights[i] for i in indexes)}', opening, count=1)
        body = ''.join(re.sub(r'(<hp:cellAddr\b[^>]*\browAddr=")\d+', rf'\g<1>{i}', rows[source]) for i, source in enumerate(indexes))
        pieces.append(opening + body + suffix)
    boundary = ('</hp:run></hp:p><hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" '
                'pageBreak="1" columnBreak="0" merged="0"><hp:run charPrIDRef="62">')
    return boundary.join(pieces)


def _cell_required_height(cell: str) -> int:
    """Measure explicit paragraphs and wrapped text; never shrink to template height."""
    width = int(re.search(r'<hp:cellSz\b[^>]*\bwidth="(\d+)"', cell).group(1))
    usable = max(TABLE_FONT_HEIGHT, width - TABLE_MARGIN_HORIZONTAL * 2)
    capacity = max(1, int(usable / TABLE_FONT_HEIGHT * .92))
    paragraphs = find_hwpx_tag_spans(cell, "hp:p")
    lines = 0
    for start, end in paragraphs:
        paragraph = cell[start:end]
        marked = re.sub(r'<hp:lineBreak\s*/>', '\n', paragraph)
        text = get_hwpx_xml_scope_text(marked).replace('<hp:lineBreak/>', '\n')
        for line in text.split('\n'):
            units = sum(1 if ord(char) > 127 else .55 for char in line)
            lines += max(1, math.ceil(units / capacity))
    return max(TABLE_ROW_MIN_HEIGHT, max(1, lines) * TABLE_LINE_HEIGHT + TABLE_CELL_MARGIN_VERTICAL * 2 + 200)


def _physical_row_height(row_xml: str) -> int:
    regular: list[int] = []
    all_heights: list[int] = []
    for start, end in find_hwpx_tag_spans(row_xml, "hp:tc"):
        cell = row_xml[start:end]
        height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
        if not height:
            continue
        value = int(height.group(1))
        all_heights.append(value)
        span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
        if not span or int(span.group(1)) == 1:
            regular.append(value)
    values = regular or all_heights
    return min(values) if values else 0


def _compact_table_row_heights_xml(table: str) -> str:
    """Rebuild content-driven physical rows and consistent merged-cell heights.

    This is idempotent: repeated conversion must not subtract padding again.
    """

    spans = find_hwpx_tag_spans(table, "hp:tr")
    if not spans:
        return table
    rows = [table[start:end] for start, end in spans]
    physical = [TABLE_ROW_MIN_HEIGHT for _ in rows]
    merged = []
    for row_index, row in enumerate(rows):
        for start, end in find_hwpx_tag_spans(row, "hp:tc"):
            cell = row[start:end]
            span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            count = max(1, int(span.group(1))) if span else 1
            required = _cell_required_height(cell)
            if count == 1:
                physical[row_index] = max(physical[row_index], required)
            else:
                merged.append((row_index, min(count, len(rows) - row_index), required))
    for row_index, count, required in merged:
        deficit = required - sum(physical[row_index:row_index + count])
        if deficit > 0:
            physical[row_index + count - 1] += deficit

    resized: list[str] = []
    for row_index, row in enumerate(rows):
        def resize_cell(match: re.Match[str]) -> str:
            cell = match.group(0)
            span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            row_span = max(1, int(span.group(1))) if span else 1
            target = sum(physical[row_index : row_index + row_span])
            return re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf"\g<1>{target}",
                cell,
                count=1,
            )

        resized.append(re.sub(r"<hp:tc\b.*?</hp:tc>", resize_cell, row, flags=re.DOTALL))

    updated = table[: spans[0][0]] + "".join(resized) + table[spans[-1][1] :]
    return re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf"\g<1>{sum(physical)}",
        updated,
        count=1,
    )


def _paragraph_text(paragraph: str) -> str:
    return re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip()


def _is_removable_empty_paragraph(paragraph: str) -> bool:
    return (
        not _paragraph_text(paragraph)
        and "<hp:tbl" not in paragraph
        and "<hp:ctrl" not in paragraph
        and "<hp:secPr" not in paragraph
    )


def normalize_project_overview_opening_xml(xml: str) -> tuple[str, bool]:
    """Remove authoring residue and anchor the overview at the page top."""

    changed = False
    paragraphs = find_hwpx_tag_spans(xml, "hp:p")
    heading_span = next(
        (
            (start, end)
            for start, end in paragraphs
            if _paragraph_text(xml[start:end]).startswith("2. 사업개요")
            and "<hp:tbl" not in xml[start:end]
        ),
        None,
    )
    if heading_span is None:
        return xml, False

    start, end = heading_span
    heading = xml[start:end]
    for note in AUTHORING_NOTES:
        heading = heading.replace(note, "")
    heading = set_hwpx_xml_scope_text(heading, CANONICAL_HEADING)
    heading = re.sub(
        r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
        r'\g<1>15\2',
        heading,
        count=1,
    )
    opening = re.match(r"<hp:p\b[^>]*>", heading)
    if opening:
        tag = opening.group(0)
        if re.search(r'\bpageBreak="[01]"', tag):
            updated_tag = re.sub(r'(\bpageBreak=")[01](")', r'\g<1>1\2', tag, count=1)
        else:
            updated_tag = tag[:-1] + ' pageBreak="1">'
        heading = updated_tag + heading[opening.end() :]
    heading_prefix, separator, heading_suffix = heading.partition("<hp:tbl")
    heading_prefix = re.sub(
        r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+("[^>]*>)',
        r'\g<1>76\2',
        heading_prefix,
    )
    heading = heading_prefix + (separator + heading_suffix if separator else "")
    if heading != xml[start:end]:
        xml = xml[:start] + heading + xml[end:]
        changed = True

    if not _PROFILE.get("remove_adjacent_empty_paragraphs", True):
        return xml, changed

    paragraphs = find_hwpx_tag_spans(xml, "hp:p")
    heading_index = next(
        (
            index
            for index, (para_start, para_end) in enumerate(paragraphs)
            if _paragraph_text(xml[para_start:para_end]) == CANONICAL_HEADING
            and "<hp:tbl" not in xml[para_start:para_end]
        ),
        -1,
    )
    if heading_index < 0:
        return xml, changed

    removable: list[tuple[int, int]] = []
    index = heading_index - 1
    while index >= 0:
        para_start, para_end = paragraphs[index]
        paragraph = xml[para_start:para_end]
        if not _is_removable_empty_paragraph(paragraph):
            break
        removable.append((para_start, para_end))
        index -= 1
    index = heading_index + 1
    while index < len(paragraphs):
        para_start, para_end = paragraphs[index]
        paragraph = xml[para_start:para_end]
        if "<hp:tbl" in paragraph:
            break
        if not _is_removable_empty_paragraph(paragraph):
            break
        removable.append((para_start, para_end))
        index += 1
    for para_start, para_end in sorted(removable, reverse=True):
        xml = xml[:para_start] + xml[para_end:]
        changed = True
    return xml, changed


def compact_project_overview_table_xml(xml: str) -> tuple[str, bool]:
    """Retain the template grid with readable widths and content-driven height."""

    # The official template visually prints "구 분" with an intentional
    # character gap, while synthetic/test templates often store "구분".
    # Identify the table by invariant labels instead of that typography.
    target = find_hwpx_table_span_by_text(xml, ["내용", "사업개요", "사업명(국문)"], 20)
    if target is None:
        return xml, False
    start, end, table = target

    def update_margin(match: re.Match[str]) -> str:
        margin = match.group(0)
        for name in ("left", "right", "top", "bottom"):
            value = TABLE_CELL_MARGIN_VERTICAL if name in ("top", "bottom") else TABLE_MARGIN_HORIZONTAL
            margin = re.sub(
                rf'(\b{name}=")\d+',
                rf'\g<1>{value}',
                margin,
                count=1,
            )
        return margin

    updated = re.sub(r"<hp:inMargin\b[^>]*/>", update_margin, table, count=1)
    updated = re.sub(r"<hp:cellMargin\b[^>]*/>", update_margin, updated)
    def resize_width(match: re.Match[str]) -> str:
        cell = match.group(0)
        column = int(re.search(r'<hp:cellAddr\b[^>]*\bcolAddr="(\d+)"', cell).group(1))
        count = int(re.search(r'<hp:cellSpan\b[^>]*\bcolSpan="(\d+)"', cell).group(1))
        width = sum(TABLE_COLUMN_WIDTHS[column:column + count])
        return re.sub(r'(<hp:cellSz\b[^>]*\bwidth=")\d+', rf'\g<1>{width}', cell, count=1)
    updated = re.sub(r'<hp:tc\b.*?</hp:tc>', resize_width, updated, flags=re.DOTALL)
    updated = re.sub(r'(<hp:sz\b[^>]*\bwidth=")\d+', rf'\g<1>{sum(TABLE_COLUMN_WIDTHS)}', updated, count=1)
    updated = _compact_table_row_heights_xml(updated)
    # This table follows a forced-page heading after variable-length section-6
    # prose. With the template's floating anchor (treatAsChar=0), kordoc can
    # retain the previous page's paragraph origin and paint the entire table
    # over that prose although rHWP moves it to the next page. Keep the table
    # in the document flow. CELL pagination still lets its rows continue; do
    # not force a fixed page count or shorten content to fit the old template.
    updated = re.sub(r'(<hp:pos\b[^>]*\btreatAsChar=")[01]', r'\g<1>1', updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r"\g<1>CELL", updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r"\g<1>1", updated, count=1)
    updated = _split_overview_at_merged_groups(updated)
    return xml[:start] + updated + xml[end:], updated != table
