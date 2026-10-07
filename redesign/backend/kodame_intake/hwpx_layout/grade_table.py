from __future__ import annotations

import math
import re

from backend.oda_me.hwpx.patchers import (
    GRADE_QUESTION_REASON_CELLS,
    GRADE_SUBTOTAL_REASON_CELLS,
    find_hwpx_grade_table_span_xml,
    find_hwpx_tag_spans,
    get_hwpx_xml_scope_text,
    set_hwpx_table_cell_char_pr_xml,
    set_hwpx_table_cell_text_xml,
)

from ..quality_profile import layout_profile
from .overflow import append_table_details, fit_table_details, oversized_group_cells


_GRADE_PROFILE = layout_profile("grade_table")


GRADE_QUESTION_ROWS = (1, 2, 4, 5, 7, 8, 9, 11, 12, 14, 15)
GRADE_SUBTOTAL_ROWS = (3, 6, 10, 13, 16)
GRADE_SUMMARY_ROWS = (17, 18, 19)
GRADE_CRITERION_ROW_GROUPS = ((1, 2, 3), (4, 5, 6), (7, 8, 9, 10), (11, 12, 13), (14, 15, 16))

GRADE_QUESTION_FONT_HEIGHT = int(_GRADE_PROFILE["font_height"])
GRADE_SINGLE_LINE_FONT_HEIGHT = 1000
GRADE_LINE_SPACING_PERCENT = int(_GRADE_PROFILE["line_spacing_percent"])
GRADE_QUESTION_LINE_HEIGHT = GRADE_QUESTION_FONT_HEIGHT * GRADE_LINE_SPACING_PERCENT // 100
GRADE_CELL_MARGIN_HORIZONTAL = int(_GRADE_PROFILE["cell_margin_horizontal"])
GRADE_CELL_MARGIN_VERTICAL = int(_GRADE_PROFILE["cell_margin_vertical"])

# Every grade-table cell uses a fixed 1pt above and below.  A one-line 10pt
# cell is therefore 13pt at 130% leading plus 2pt total vertical padding.
# Question rows use the same formula with 9pt body text and are calculated
# from the actual wrapped line count below.
GRADE_HEADER_ROW_HEIGHT = (
    GRADE_SINGLE_LINE_FONT_HEIGHT * GRADE_LINE_SPACING_PERCENT // 100
    + GRADE_CELL_MARGIN_VERTICAL * 2
)
GRADE_QUESTION_MIN_HEIGHT = GRADE_QUESTION_LINE_HEIGHT * 2 + GRADE_CELL_MARGIN_VERTICAL * 2
# A long rationale is measured in full. This is an acceptance bound after
# lossless overflow handling, never a cap on the measured content height.
GRADE_QUESTION_MAX_HEIGHT = 65000 - GRADE_HEADER_ROW_HEIGHT * 2
GRADE_SUBTOTAL_ROW_HEIGHT = GRADE_HEADER_ROW_HEIGHT
GRADE_SUMMARY_ROW_HEIGHT = GRADE_HEADER_ROW_HEIGHT

# These questions are the fixed KOICA evaluation framework, not generated
# project content.  Explicit semantic breaks follow published evaluation
# reports: modifiers stay with their nouns and the predicate closes the row.
GRADE_QUESTION_TEXTS: dict[int, str] = {
    5: (
        "· 사업은 이해관계자의 주요 정책 및 수요(needs),\n"
        "우선순위를 반영하여 설계(design)되었는가?"
    ),
    9: (
        "· 내·외부 상황변화에 맞추어 사업 설계를\n"
        "적절히 관리 및 유지하였는가?"
    ),
    18: (
        "· (내적 일관성) 한국 정부, 국내 타 기관,\n"
        "유관 ODA 사업, 주요 국제규범 및 기준과의\n"
        "상호보완성, 조화·조율, 부가가치를 고려하여\n"
        "사업을 추진하였는가?"
    ),
    22: (
        "· (외적 일관성) 현지 내 타 주체(타 공여기관,\n"
        "수원국 정부 및 민간분야)의 개입과 상호보완성,\n"
        "조화·조율, 부가가치를 고려하여\n"
        "사업을 추진하였는가?"
    ),
    31: (
        "· 사업의 직접적·일차적 산출물(output)을\n"
        "계획한 대로 달성하였는가?"
    ),
    35: (
        "· 사업의 중장기 성과(outcome) 및 목표(goal)를\n"
        "달성하였거나 달성할 것으로 예상하는가?"
    ),
    39: (
        "· 해당 사업이 사회적 소외계층을 포용하여\n"
        "형평성 있게 성과를 달성하였는가?"
    ),
    48: (
        "· 사업은 경제적이고 시의적절한 방식으로\n"
        "추진되었는가?"
    ),
    52: (
        "· 사업은 주요 투입 및 활동 간 균형과 상호작용을\n"
        "고려하여 효율적으로 추진되었는가?"
    ),
    61: (
        "· 수원국 내 시스템, 조직 및 이해관계자는\n"
        "사업 편익이 지속될 수 있는 재정적·경제적\n"
        "자립역량 및 위기대응능력을 갖추었는가?"
    ),
    65: (
        "· 사업 편익이 장기적으로 지속될 수 있는\n"
        "제도적·사회적 환경이 갖추어졌는가?"
    ),
}
GRADE_QUESTION_CELLS = tuple(GRADE_QUESTION_TEXTS)
GRADE_TABLE_PAGE_ROW_GROUPS = tuple(
    tuple(int(row) for row in group)
    for group in _GRADE_PROFILE["page_row_groups"]
)


def _set_table_cell_para_pr_xml(table_xml: str, cell_index: int, para_pr_id: int) -> str:
    cells = find_hwpx_tag_spans(table_xml, "hp:tc")
    if not 0 <= cell_index < len(cells):
        return table_xml
    start, end = cells[cell_index]
    cell = re.sub(
        r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
        rf"\g<1>{para_pr_id}\2",
        table_xml[start:end],
    )
    return table_xml[:start] + cell + table_xml[end:]


def _strip_table_cell_tabs_xml(table_xml: str, cell_index: int) -> str:
    cells = find_hwpx_tag_spans(table_xml, "hp:tc")
    if not 0 <= cell_index < len(cells):
        return table_xml
    start, end = cells[cell_index]
    cell = table_xml[start:end]
    cell = re.sub(r"<hp:tab\b[^>]*/>", "", cell)
    cell = cell.replace("\t", " ")
    return table_xml[:start] + cell + table_xml[end:]


def _set_grade_table_margin_xml(table_xml: str) -> str:
    """Give every cell print-safe padding through the table default margin."""

    match = re.search(r"<hp:inMargin\b[^>]*/>", table_xml)
    if not match:
        return table_xml
    margin = match.group(0)
    for name, value in (
        ("left", GRADE_CELL_MARGIN_HORIZONTAL),
        ("right", GRADE_CELL_MARGIN_HORIZONTAL),
        ("top", GRADE_CELL_MARGIN_VERTICAL),
        ("bottom", GRADE_CELL_MARGIN_VERTICAL),
    ):
        margin = re.sub(rf'(\b{name}=")\d+("?)', rf"\g<1>{value}\2", margin, count=1)
    return table_xml[: match.start()] + margin + table_xml[match.end() :]


def _grade_text_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _grade_cell_line_count(cell_xml: str, chars_per_line: int) -> int:
    marker = "\ue000"
    marked = re.sub(r"<hp:lineBreak\s*/>", marker, cell_xml)
    text = get_hwpx_xml_scope_text(marked)
    lines = [re.sub(r"\s+", " ", part).strip() for part in text.split(marker)]
    return max(
        1,
        sum(max(1, math.ceil(_grade_text_units(line) / chars_per_line)) for line in lines if line),
    )


def grade_question_row_height(row_xml: str) -> int:
    """Return content height plus fixed 1pt padding above and below."""

    line_count = 1
    for start, end in find_hwpx_tag_spans(row_xml, "hp:tc"):
        cell = row_xml[start:end]
        address = re.search(r'<hp:cellAddr\b[^>]*\bcolAddr="(\d+)"', cell)
        if not address or int(address.group(1)) not in {1, 4}:
            continue
        chars_per_line = 18 if address.group(1) == "1" else 17
        line_count = max(line_count, _grade_cell_line_count(cell, chars_per_line))
    return max(GRADE_QUESTION_MIN_HEIGHT,
               line_count * GRADE_QUESTION_LINE_HEIGHT + GRADE_CELL_MARGIN_VERTICAL * 2)


def _resize_grade_table_rows_xml(table_xml: str) -> str:
    rows = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(rows) < 20:
        return table_xml

    heights = {
        0: GRADE_HEADER_ROW_HEIGHT,
        **{row: GRADE_SUBTOTAL_ROW_HEIGHT for row in GRADE_SUBTOTAL_ROWS},
        **{row: GRADE_SUMMARY_ROW_HEIGHT for row in GRADE_SUMMARY_ROWS},
    }
    for row_index in GRADE_QUESTION_ROWS:
        start, end = rows[row_index]
        heights[row_index] = grade_question_row_height(table_xml[start:end])
    group_heights = {
        group[0]: sum(heights[row_index] for row_index in group)
        for group in GRADE_CRITERION_ROW_GROUPS
    }

    updated = table_xml
    for row_index, (start, end) in reversed(list(enumerate(rows))):
        row_xml = updated[start:end]

        def resize_cell(match: re.Match[str]) -> str:
            cell = match.group(0)
            row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            target_height = (
                group_heights.get(row_index, heights.get(row_index, GRADE_HEADER_ROW_HEIGHT))
                if row_span and int(row_span.group(1)) > 1
                else heights.get(row_index, GRADE_HEADER_ROW_HEIGHT)
            )
            return re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf"\g<1>{target_height}",
                cell,
                count=1,
            )

        resized = re.sub(r"<hp:tc\b.*?</hp:tc>", resize_cell, row_xml, flags=re.DOTALL)
        updated = updated[:start] + resized + updated[end:]
    total_height = sum(heights[row_index] for row_index in range(len(rows)))
    return re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf"\g<1>{total_height}",
        updated,
        count=1,
    )


def grade_page_row_groups(row_xml: list[str]) -> tuple[tuple[int, ...], ...]:
    """Keep the preferred two-page layout when it fits; otherwise pack whole criteria.

    Criterion labels span their question/subtotal rows. Never break those merged
    cells or discard rationale text to satisfy a fixed page count.
    """
    heights = [min(map(int, re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row))) for row in row_xml]
    if all(sum(heights[i] for i in group) <= (58000 if page == 0 else 65000)
           for page, group in enumerate(GRADE_TABLE_PAGE_ROW_GROUPS)):
        return GRADE_TABLE_PAGE_ROW_GROUPS
    pages = []
    current = [0]
    height = heights[0]
    for group in (*GRADE_CRITERION_ROW_GROUPS, GRADE_SUMMARY_ROWS):
        needed = sum(heights[i] for i in group)
        budget = 58000 if not pages else 65000
        if len(current) > 1 and height + needed > budget:
            pages.append(tuple(current))
            current, height = [0], heights[0]
        current.extend(group)
        height += needed
    if len(current) > 1:
        pages.append(tuple(current))
    return tuple(pages)


def _split_grade_table_into_pages_xml(table_xml: str) -> str:
    """Create page-sized tables, preserving complete criterion groups."""

    rows = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(rows) != 20:
        return table_xml
    prefix = table_xml[: rows[0][0]]
    suffix = table_xml[rows[-1][1] :]
    base_id_match = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)
    base_id = int(base_id_match.group(1)) if base_id_match else 1243405073
    row_xml = [table_xml[start:end] for start, end in rows]
    parts: list[str] = []
    for part_index, row_indexes in enumerate(grade_page_row_groups(row_xml)):
        part_prefix = re.sub(
            r'(<hp:tbl\b[^>]*\bid=")\d+',
            rf"\g<1>{base_id + part_index}",
            prefix,
            count=1,
        )
        part_prefix = re.sub(
            r'(<hp:tbl\b[^>]*\browCnt=")\d+',
            rf"\g<1>{len(row_indexes)}",
            part_prefix,
            count=1,
        )
        selected_rows = [
            re.sub(
                r'(<hp:cellAddr\b[^>]*\browAddr=")\d+',
                rf"\g<1>{new_row_index}",
                row_xml[source_row_index],
            )
            for new_row_index, source_row_index in enumerate(row_indexes)
        ]
        part_height = sum(
            min(int(value) for value in re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row))
            for row in selected_rows
        )
        part_prefix = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+',
            rf"\g<1>{part_height}",
            part_prefix,
            count=1,
        )
        parts.append(part_prefix + "".join(selected_rows) + suffix)

    page_break = (
        '</hp:run></hp:p>'
        '<hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" '
        'pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="62">'
    )
    return page_break.join(parts)


def style_grade_table_xml(xml: str) -> tuple[str, bool]:
    """Format the grade table with fixed 1pt vertical padding."""

    span = find_hwpx_grade_table_span_xml(xml)
    if span is None:
        return xml, False
    start, end = span
    table = xml[start:end]
    # CELL lets Hancom continue the table on the next page; TABLE attempts to
    # keep this oversized table together and can push its lower rows off-page.
    updated = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r"\g<1>CELL", table, count=1)
    # Keep the authored row heights.  With noAdjust=0 Hancom compresses the
    # rows back to their text minimum and visually removes the intended air.
    updated = re.sub(r'(<hp:tbl\b[^>]*\bnoAdjust=")[^"]+', r"\g<1>1", updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r"\g<1>1", updated, count=1)
    updated = _set_grade_table_margin_xml(updated)

    for cell_index, question in GRADE_QUESTION_TEXTS.items():
        updated, _ = set_hwpx_table_cell_text_xml(
            updated,
            cell_index,
            question,
            preserve_line_breaks=True,
        )
        updated = set_hwpx_table_cell_char_pr_xml(updated, cell_index, 92)
        updated = _set_table_cell_para_pr_xml(updated, cell_index, 39)
        updated = _strip_table_cell_tabs_xml(updated, cell_index)

    for cell_index in (*GRADE_QUESTION_REASON_CELLS, *GRADE_SUBTOTAL_REASON_CELLS):
        updated = set_hwpx_table_cell_char_pr_xml(updated, cell_index, 92)
        updated = _set_table_cell_para_pr_xml(updated, cell_index, 39)
        updated = _strip_table_cell_tabs_xml(updated, cell_index)
    for cell_index in GRADE_SUBTOTAL_REASON_CELLS:
        updated, _ = set_hwpx_table_cell_text_xml(updated, cell_index, "")

    # Merged criterion cells must stay together. If even one complete criterion
    # cannot fit, preserve its full oversized cell in paginated detail prose.
    # Measuring before relocation prevents the old nine-line height clamp from
    # hiding overflow from both page packing and validation.
    groups = [(0, *group) for group in GRADE_CRITERION_ROW_GROUPS]
    def overflowing(value):
        measured = _resize_grade_table_rows_xml(value)
        return (oversized_group_cells(measured, groups[:1], 58000)
                | oversized_group_cells(measured, groups[1:], 65000))
    updated, details = fit_table_details(
        updated, overflowing, '평가등급',
    )
    updated = _resize_grade_table_rows_xml(updated)
    updated = _split_grade_table_into_pages_xml(updated)
    updated = append_table_details(updated, details)
    return xml[:start] + updated + xml[end:], updated != table
