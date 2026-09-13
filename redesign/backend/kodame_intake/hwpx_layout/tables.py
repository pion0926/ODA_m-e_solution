from __future__ import annotations

import math
import re
from html import escape

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans,
    find_hwpx_table_span_by_text,
    get_hwpx_xml_scope_text,
    set_hwpx_table_cell_char_pr_xml,
    set_hwpx_table_cell_text_xml,
)

from .grade_table import style_grade_table_xml
from ..quality_profile import layout_profile


_PDM_PROFILE = layout_profile("pdm_table")
_ACHIEVEMENT_PROFILE = layout_profile("achievement_table")
_EVALUATION_MATRIX_PROFILE = layout_profile("evaluation_matrix_table")


PDM_HEADER_CELLS = (0, 1, 2, 3)
PDM_ROW_LABEL_CELLS = (4, 9, 14, 19, 20, 21)
PDM_BODY_CELLS = (5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 22, 23, 24)

ACHIEVEMENT_HEADER_ROW_COUNT = 3
ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM = 3
ACHIEVEMENT_FONT_HEIGHT = int(_ACHIEVEMENT_PROFILE["font_height"])
ACHIEVEMENT_LINE_SPACING_PERCENT = int(_ACHIEVEMENT_PROFILE["line_spacing_percent"])
ACHIEVEMENT_LINE_HEIGHT = ACHIEVEMENT_FONT_HEIGHT * ACHIEVEMENT_LINE_SPACING_PERCENT // 100
ACHIEVEMENT_CELL_MARGIN_VERTICAL = int(_ACHIEVEMENT_PROFILE["cell_margin_vertical"])
ACHIEVEMENT_HEADER_ROW_HEIGHTS = tuple(
    int(value) for value in _ACHIEVEMENT_PROFILE["header_row_heights"]
)
ACHIEVEMENT_GROUP_MIN_HEIGHT = 5400
ACHIEVEMENT_PHYSICAL_ROW_MIN_HEIGHT = ACHIEVEMENT_GROUP_MIN_HEIGHT // 3
ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS = tuple(
    tuple(int(item) for item in group)
    for group in _ACHIEVEMENT_PROFILE["page_item_groups"]
)

PDM_TABLE_PAGE_ROW_GROUPS = tuple(
    tuple(int(row) for row in group)
    for group in _PDM_PROFILE["page_row_groups"]
)
PDM_COLUMN_WIDTHS = tuple(int(width) for width in _PDM_PROFILE["column_widths"])
PDM_HEADER_LABELS = tuple(str(label) for label in _PDM_PROFILE["header_labels"])
PDM_CELL_MARGIN_HORIZONTAL = int(_PDM_PROFILE["cell_margin_horizontal"])
PDM_CELL_MARGIN_VERTICAL = int(_PDM_PROFILE["cell_margin_vertical"])
PDM_FONT_HEIGHT = int(_PDM_PROFILE["font_height"])
PDM_LINE_SPACING_PERCENT = int(_PDM_PROFILE["line_spacing_percent"])
PDM_LINE_HEIGHT = PDM_FONT_HEIGHT * PDM_LINE_SPACING_PERCENT // 100
PDM_HEADER_ROW_HEIGHT = int(_PDM_PROFILE["header_row_height"])
PDM_LEVEL_LABEL_ROW_HEIGHT = int(_PDM_PROFILE["level_label_row_height"])
PDM_MINIMUM_GROUP_HEIGHT = int(_PDM_PROFILE["minimum_group_height"])
PDM_MAXIMUM_TABLE_HEIGHT = int(_PDM_PROFILE["maximum_table_height"])

EVALUATION_MATRIX_HEADER_ROW_COUNT = 1
EVALUATION_MATRIX_FONT_HEIGHT = int(_EVALUATION_MATRIX_PROFILE["font_height"])
EVALUATION_MATRIX_LINE_SPACING_PERCENT = int(
    _EVALUATION_MATRIX_PROFILE["line_spacing_percent"]
)
EVALUATION_MATRIX_LINE_HEIGHT = (
    EVALUATION_MATRIX_FONT_HEIGHT * EVALUATION_MATRIX_LINE_SPACING_PERCENT // 100
)
EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL = int(
    _EVALUATION_MATRIX_PROFILE["cell_margin_horizontal"]
)
EVALUATION_MATRIX_CELL_MARGIN_VERTICAL = int(
    _EVALUATION_MATRIX_PROFILE["cell_margin_vertical"]
)
EVALUATION_MATRIX_HEADER_ROW_HEIGHT = int(
    _EVALUATION_MATRIX_PROFILE["header_row_height"]
)
EVALUATION_MATRIX_BODY_MIN_HEIGHT = (
    EVALUATION_MATRIX_LINE_HEIGHT * 2 + EVALUATION_MATRIX_CELL_MARGIN_VERTICAL * 2
)
EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS = tuple(
    tuple(int(row) for row in group)
    for group in _EVALUATION_MATRIX_PROFILE["page_row_groups"]
)
EVALUATION_MATRIX_CRITERION_LABELS = (
    "1. 적절성",
    "2. 일관성",
    "3. 효과성",
    "4. 효율성",
    "5. 지속가능성 (준비도)",
    "6. 인권·취약계층 주류화 (해당 시)",
    "7. 성주류화 (해당 시)",
    "8. 환경주류화",
)


def _achievement_text_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _achievement_cell_line_count(cell_xml: str) -> int:
    marker = "\ue000"
    marked = re.sub(r"<hp:lineBreak\s*/>", marker, cell_xml)
    text = re.sub(r"<[^>]+>", "", get_hwpx_xml_scope_text(marked))
    width_match = re.search(r'<hp:cellSz\b[^>]*\bwidth="(\d+)"', cell_xml)
    width = int(width_match.group(1)) if width_match else 8000
    chars_per_line = max(4, (width - 400) // ACHIEVEMENT_FONT_HEIGHT)
    lines = [re.sub(r"\s+", " ", part).strip() for part in text.split(marker)]
    return max(
        1,
        sum(max(1, math.ceil(_achievement_text_units(line) / chars_per_line)) for line in lines if line),
    )


def _achievement_cell_required_height(cell_xml: str) -> int:
    return (
        _achievement_cell_line_count(cell_xml) * ACHIEVEMENT_LINE_HEIGHT
        + ACHIEVEMENT_CELL_MARGIN_VERTICAL * 2
        + 120
    )


def achievement_item_group_physical_heights(group_rows: list[str] | tuple[str, ...]) -> tuple[int, int, int]:
    """Size all three physical rows from every cell in an indicator group.

    The original implementation inspected only the first physical row.  In
    the achievement template, target/midline/endline and verification cells
    also live in rows two and three.  A long value in either row therefore
    kept the old one-third height and Hancom vertically squeezed or overlaid
    its lines.  This routine measures regular cells row-by-row and then grows
    the covered rows for every row-spanning cell.
    """

    rows = list(group_rows[:ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM])
    if len(rows) != ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
        return (ACHIEVEMENT_PHYSICAL_ROW_MIN_HEIGHT,) * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM

    heights = [ACHIEVEMENT_PHYSICAL_ROW_MIN_HEIGHT] * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
    spanning_requirements: list[tuple[int, int, int]] = []
    for row_offset, row_xml in enumerate(rows):
        for start, end in find_hwpx_tag_spans(row_xml, "hp:tc"):
            cell = row_xml[start:end]
            if not get_hwpx_xml_scope_text(cell).strip():
                continue
            required_height = _achievement_cell_required_height(cell)
            row_span_match = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            row_span = int(row_span_match.group(1)) if row_span_match else 1
            if row_span <= 1:
                heights[row_offset] = max(heights[row_offset], required_height)
            else:
                spanning_requirements.append(
                    (
                        row_offset,
                        min(ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM, row_offset + row_span),
                        required_height,
                    )
                )

    def distribute(shortfall: int, start: int, stop: int) -> None:
        if shortfall <= 0 or stop <= start:
            return
        count = stop - start
        per_row, remainder = divmod(shortfall, count)
        for offset in range(start, stop):
            heights[offset] += per_row + (1 if offset - start < remainder else 0)

    for start, stop, required_height in spanning_requirements:
        distribute(required_height - sum(heights[start:stop]), start, stop)
    distribute(ACHIEVEMENT_GROUP_MIN_HEIGHT - sum(heights), 0, len(heights))
    return tuple(heights)  # type: ignore[return-value]


def achievement_item_group_height(row_xml: str) -> int:
    """Calculate one indicator group's height from all available rows."""

    row_spans = find_hwpx_tag_spans(row_xml, "hp:tr")
    if len(row_spans) >= ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
        rows = [row_xml[start:end] for start, end in row_spans[:ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM]]
        return sum(achievement_item_group_physical_heights(rows))
    cell_heights = [
        _achievement_cell_required_height(row_xml[start:end])
        for start, end in find_hwpx_tag_spans(row_xml, "hp:tc")
        if get_hwpx_xml_scope_text(row_xml[start:end]).strip()
    ]
    return max(ACHIEVEMENT_GROUP_MIN_HEIGHT, max(cell_heights, default=0))


def _physical_row_height(row_xml: str) -> int:
    regular_heights: list[int] = []
    all_heights: list[int] = []
    for start, end in find_hwpx_tag_spans(row_xml, "hp:tc"):
        cell = row_xml[start:end]
        height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
        if not height:
            continue
        all_heights.append(int(height.group(1)))
        row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
        if not row_span or int(row_span.group(1)) == 1:
            regular_heights.append(int(height.group(1)))
    heights = regular_heights or all_heights
    return min(heights) if heights else 0


def _resize_achievement_table_rows_xml(table_xml: str) -> str:
    """Normalize all 3-row indicator groups, including originally zero-height rows."""

    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) <= ACHIEVEMENT_HEADER_ROW_COUNT:
        return table_xml
    rows = [table_xml[start:end] for start, end in spans]
    body_count = len(rows) - ACHIEVEMENT_HEADER_ROW_COUNT
    if body_count % ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
        return table_xml

    for row_index, physical_height in enumerate(ACHIEVEMENT_HEADER_ROW_HEIGHTS):
        def resize_header_cell(match: re.Match[str]) -> str:
            cell = match.group(0)
            row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            span_count = int(row_span.group(1)) if row_span else 1
            target_height = sum(
                ACHIEVEMENT_HEADER_ROW_HEIGHTS[
                    row_index : min(
                        len(ACHIEVEMENT_HEADER_ROW_HEIGHTS),
                        row_index + span_count,
                    )
                ]
            )
            return re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf"\g<1>{target_height}",
                cell,
                count=1,
            )

        rows[row_index] = re.sub(
            r"<hp:tc\b.*?</hp:tc>",
            resize_header_cell,
            rows[row_index],
            flags=re.DOTALL,
        )

    body_heights: dict[int, int] = {}
    for group_start in range(
        ACHIEVEMENT_HEADER_ROW_COUNT,
        len(rows),
        ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
    ):
        group_rows = rows[group_start : group_start + ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM]
        physical_heights = achievement_item_group_physical_heights(group_rows)
        group_height = sum(physical_heights)
        for offset, physical_height in enumerate(physical_heights):
            row_index = group_start + offset
            body_heights[row_index] = physical_height

            def resize_cell(match: re.Match[str]) -> str:
                cell = match.group(0)
                row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
                span_count = int(row_span.group(1)) if row_span else 1
                target_height = (
                    sum(physical_heights[offset : min(len(physical_heights), offset + span_count)])
                    if span_count > 1
                    else physical_height
                )
                return re.sub(
                    r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                    rf"\g<1>{target_height}",
                    cell,
                    count=1,
                )

            rows[row_index] = re.sub(
                r"<hp:tc\b.*?</hp:tc>",
                resize_cell,
                rows[row_index],
                flags=re.DOTALL,
            )

    prefix = table_xml[: spans[0][0]]
    suffix = table_xml[spans[-1][1] :]
    updated = prefix + "".join(rows) + suffix
    total_height = sum(ACHIEVEMENT_HEADER_ROW_HEIGHTS)
    total_height += sum(
        body_heights[index]
        for index in range(ACHIEVEMENT_HEADER_ROW_COUNT, len(rows))
    )
    return re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf"\g<1>{total_height}",
        updated,
        count=1,
    )


def achievement_page_groups(item_count: int) -> tuple[tuple[int, ...], ...]:
    capacity = max(len(group) for group in ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS)
    # Reserve space for the chapter heading on the first landscape page.
    first = min(capacity - 1, item_count)
    if first <= 0:
        return ()
    return (tuple(range(first)),) + tuple(tuple(range(start, min(start + capacity, item_count))) for start in range(first, item_count, capacity))


def _split_achievement_table_into_pages_xml(table_xml: str) -> str:
    """Split the current PDM indicator count; 14 is not a universal contract."""

    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    body_count = len(spans) - ACHIEVEMENT_HEADER_ROW_COUNT
    if body_count <= 0 or body_count % ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
        return table_xml
    groups = achievement_page_groups(body_count // ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM)
    prefix = table_xml[: spans[0][0]]
    suffix = table_xml[spans[-1][1] :]
    rows = [table_xml[start:end] for start, end in spans]
    base_id_match = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)
    base_id = int(base_id_match.group(1)) if base_id_match else 1794292357
    parts: list[str] = []
    for part_index, item_indexes in enumerate(groups):
        row_indexes = list(range(ACHIEVEMENT_HEADER_ROW_COUNT))
        for item_index in item_indexes:
            item_start = ACHIEVEMENT_HEADER_ROW_COUNT + (
                item_index * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
            )
            row_indexes.extend(
                range(item_start, item_start + ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM)
            )
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
                rows[source_row_index],
            )
            for new_row_index, source_row_index in enumerate(row_indexes)
        ]
        part_height = sum(_physical_row_height(row) for row in selected_rows)
        part_prefix = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+',
            rf"\g<1>{part_height}",
            part_prefix,
            count=1,
        )
        parts.append(part_prefix + "".join(selected_rows) + suffix)

    page_break = (
        "</hp:run></hp:p>"
        '<hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" '
        'pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="62">'
    )
    return page_break.join(parts)


def _set_pdm_geometry_xml(table_xml: str) -> str:
    """Apply reviewed column widths, concise headers, and print-safe margins."""

    for cell_index, label in enumerate(PDM_HEADER_LABELS):
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, cell_index, label)

    def update_cell(match: re.Match[str]) -> str:
        cell = match.group(0)
        address = re.search(r'<hp:cellAddr\b[^>]*\bcolAddr="(\d+)"', cell)
        span = re.search(r'<hp:cellSpan\b[^>]*\bcolSpan="(\d+)"', cell)
        if address and int(address.group(1)) < len(PDM_COLUMN_WIDTHS):
            column_index = int(address.group(1))
            column_span = int(span.group(1)) if span else 1
            width = sum(PDM_COLUMN_WIDTHS[column_index : column_index + column_span])
            cell = re.sub(
                r'(<hp:cellSz\b[^>]*\bwidth=")\d+',
                rf'\g<1>{width}',
                cell,
                count=1,
            )
        cell = re.sub(
            r'<hp:cellMargin\b[^>]*/>',
            (
                f'<hp:cellMargin left="{PDM_CELL_MARGIN_HORIZONTAL}" '
                f'right="{PDM_CELL_MARGIN_HORIZONTAL}" top="{PDM_CELL_MARGIN_VERTICAL}" '
                f'bottom="{PDM_CELL_MARGIN_VERTICAL}"/>'
            ),
            cell,
        )
        return cell

    table_xml = re.sub(r'<hp:tc\b.*?</hp:tc>', update_cell, table_xml, flags=re.DOTALL)
    table_xml = re.sub(
        r'<hp:inMargin\b[^>]*/>',
        (
            f'<hp:inMargin left="{PDM_CELL_MARGIN_HORIZONTAL}" '
            f'right="{PDM_CELL_MARGIN_HORIZONTAL}" top="{PDM_CELL_MARGIN_VERTICAL}" '
            f'bottom="{PDM_CELL_MARGIN_VERTICAL}"/>'
        ),
        table_xml,
        count=1,
    )
    table_xml = table_xml.replace('lineWrap="BREAK"', 'lineWrap="SQUEEZE"')
    for phrase in ("MCI Triage", "Pre-hospital", "Master Instructor", "Job Code"):
        table_xml = table_xml.replace(phrase, phrase.replace(" ", "\u00a0"))
    return table_xml


def _pdm_text_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _pdm_cell_line_count(cell_xml: str) -> int:
    marker = "\ue000"
    marked = re.sub(r"<hp:lineBreak\s*/>", marker, cell_xml)
    text = re.sub(r"<[^>]+>", "", get_hwpx_xml_scope_text(marked))
    width_match = re.search(r'<hp:cellSz\b[^>]*\bwidth="(\d+)"', cell_xml)
    width = int(width_match.group(1)) if width_match else 10000
    usable_width = max(PDM_FONT_HEIGHT * 5, width - PDM_CELL_MARGIN_HORIZONTAL * 2)
    characters_per_line = max(5, usable_width // PDM_FONT_HEIGHT)
    lines = [re.sub(r"\s+", " ", part).strip() for part in text.split(marker)]
    return max(
        1,
        sum(
            max(1, math.ceil(_pdm_text_units(line) / characters_per_line))
            for line in lines
            if line
        ),
    )


def _pdm_cell_required_height(cell_xml: str) -> int:
    return (
        _pdm_cell_line_count(cell_xml) * PDM_LINE_HEIGHT
        + PDM_CELL_MARGIN_VERTICAL * 2
        + 120
    )


def _resize_pdm_rows_xml(table_xml: str) -> str:
    """Rebuild the source PDM's four logical levels as one compact A4 table."""

    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) != 9:
        return table_xml
    rows = [table_xml[start:end] for start, end in spans]
    physical_heights = [PDM_HEADER_ROW_HEIGHT] + [0] * 8

    def resize_row_cells(
        row_xml: str,
        *,
        physical_height: int,
        spanned_height: int | None = None,
    ) -> str:
        def resize_cell(match: re.Match[str]) -> str:
            cell = match.group(0)
            row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
            target_height = (
                spanned_height
                if spanned_height is not None
                and row_span
                and int(row_span.group(1)) > 1
                else physical_height
            )
            return re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf"\g<1>{target_height}",
                cell,
                count=1,
            )

        return re.sub(r"<hp:tc\b.*?</hp:tc>", resize_cell, row_xml, flags=re.DOTALL)

    rows[0] = resize_row_cells(rows[0], physical_height=PDM_HEADER_ROW_HEIGHT)
    for label_row_index, body_row_index in ((1, 2), (3, 4), (5, 6), (7, 8)):
        label_cells = [
            rows[label_row_index][start:end]
            for start, end in find_hwpx_tag_spans(rows[label_row_index], "hp:tc")
        ]
        body_cells = [
            rows[body_row_index][start:end]
            for start, end in find_hwpx_tag_spans(rows[body_row_index], "hp:tc")
        ]
        body_requirement = max(
            (_pdm_cell_required_height(cell) for cell in body_cells),
            default=PDM_LINE_HEIGHT,
        )
        spanned_requirement = max(
            (
                _pdm_cell_required_height(cell)
                for cell in label_cells
                if re.search(r'<hp:cellSpan\b[^>]*\browSpan="[2-9]\d*"', cell)
            ),
            default=0,
        )
        group_height = max(
            PDM_MINIMUM_GROUP_HEIGHT,
            PDM_LEVEL_LABEL_ROW_HEIGHT + body_requirement,
            spanned_requirement,
        )
        body_height = group_height - PDM_LEVEL_LABEL_ROW_HEIGHT
        physical_heights[label_row_index] = PDM_LEVEL_LABEL_ROW_HEIGHT
        physical_heights[body_row_index] = body_height
        rows[label_row_index] = resize_row_cells(
            rows[label_row_index],
            physical_height=PDM_LEVEL_LABEL_ROW_HEIGHT,
            spanned_height=group_height,
        )
        rows[body_row_index] = resize_row_cells(
            rows[body_row_index],
            physical_height=body_height,
        )

    total_height = sum(physical_heights)
    updated = table_xml[: spans[0][0]] + "".join(rows) + table_xml[spans[-1][1] :]
    return re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf"\g<1>{total_height}",
        updated,
        count=1,
    )


def _split_pdm_table_into_pages_xml(table_xml: str) -> str:
    """Keep each PDM result level intact and repeat the concise header."""

    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) != 9:
        return table_xml
    prefix = table_xml[: spans[0][0]]
    suffix = table_xml[spans[-1][1] :]
    rows = [table_xml[start:end] for start, end in spans]
    base_id_match = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)
    base_id = int(base_id_match.group(1)) if base_id_match else 1794292292
    parts: list[str] = []
    for part_index, row_indexes in enumerate(PDM_TABLE_PAGE_ROW_GROUPS):
        part_prefix = re.sub(
            r'(<hp:tbl\b[^>]*\bid=")\d+',
            rf'\g<1>{base_id + part_index}',
            prefix,
            count=1,
        )
        part_prefix = re.sub(
            r'(<hp:tbl\b[^>]*\browCnt=")\d+',
            rf'\g<1>{len(row_indexes)}',
            part_prefix,
            count=1,
        )
        selected_rows = [
            re.sub(
                r'(<hp:cellAddr\b[^>]*\browAddr=")\d+',
                rf'\g<1>{new_row_index}',
                rows[source_row_index],
            )
            for new_row_index, source_row_index in enumerate(row_indexes)
        ]
        part_height = sum(_physical_row_height(row) for row in selected_rows)
        part_prefix = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+',
            rf'\g<1>{part_height}',
            part_prefix,
            count=1,
        )
        parts.append(part_prefix + "".join(selected_rows) + suffix)
    page_break = (
        "</hp:run></hp:p>"
        '<hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" '
        'pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="62">'
    )
    return page_break.join(parts)


def _set_achievement_margins_xml(table_xml: str) -> str:
    def update_margin(match: re.Match[str]) -> str:
        margin = match.group(0)
        for name in ("top", "bottom"):
            margin = re.sub(
                rf'(\b{name}=")\d+',
                rf'\g<1>{ACHIEVEMENT_CELL_MARGIN_VERTICAL}',
                margin,
                count=1,
            )
        return margin

    table_xml = re.sub(r'<hp:inMargin\b[^>]*/>', update_margin, table_xml, count=1)
    return re.sub(r'<hp:cellMargin\b[^>]*/>', update_margin, table_xml)


def _remove_empty_achievement_body_paragraphs_xml(table_xml: str) -> str:
    """Drop placeholder-only paragraphs before measuring achievement rows.

    Several row-spanning source cells contain one authored paragraph followed
    by two empty template paragraphs.  Hancom still allocates line boxes for
    those empty paragraphs, then squeezes the visible wrapped text into the
    fixed merged-cell height.  Removing only structurally empty body
    paragraphs preserves the content while avoiding both wasted height and
    native HWP line overlap.
    """

    def clean_cell(match: re.Match[str]) -> str:
        cell = match.group(0)
        address = re.search(r'<hp:cellAddr\b[^>]*\browAddr="(\d+)"', cell)
        if not address or int(address.group(1)) < ACHIEVEMENT_HEADER_ROW_COUNT:
            return cell
        # Top alignment makes the content-driven height deterministic across
        # Hancom, rHWP, and kordoc.  CENTER distributes spare height above and
        # below differently per renderer and allowed the last line of one
        # merged group to approach the first line of the next group.
        cell = re.sub(
            r'(<hp:subList\b[^>]*\bvertAlign=")[^"]+',
            r'\g<1>TOP',
            cell,
            count=1,
        )
        paragraphs = find_hwpx_tag_spans(cell, "hp:p")
        if len(paragraphs) <= 1:
            return cell
        removable: list[tuple[int, int]] = []
        for start, end in paragraphs:
            paragraph = cell[start:end]
            if get_hwpx_xml_scope_text(paragraph).strip():
                continue
            if any(token in paragraph for token in ("<hp:lineBreak", "<hp:ctrl", "<hp:pic", "<hp:tbl")):
                continue
            removable.append((start, end))
        # Keep one paragraph even in a deliberately blank cell.
        maximum_removals = max(0, len(paragraphs) - 1)
        for start, end in reversed(removable[:maximum_removals]):
            cell = cell[:start] + cell[end:]
        return cell

    return re.sub(r"<hp:tc\b.*?</hp:tc>", clean_cell, table_xml, flags=re.DOTALL)

def style_pdm_table_xml(xml: str) -> tuple[str, bool]:
    """Match the authoritative one-page A4 PDM while preserving every source cell."""

    target = find_hwpx_table_span_by_text(xml, ["프로그램 요약", "객관적 검증지표", "중요가정"], 20)
    if target is None:
        return xml, False
    start, end, table = target
    table = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r'\g<1>CELL', table, count=1)
    table = re.sub(r'(<hp:tbl\b[^>]*\bnoAdjust=")[^"]+', r'\g<1>1', table, count=1)
    table = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r'\g<1>1', table, count=1)
    table = _set_pdm_geometry_xml(table)
    for cell_index in (*PDM_HEADER_CELLS, *PDM_ROW_LABEL_CELLS):
        table = set_hwpx_table_cell_char_pr_xml(table, cell_index, 44)  # 8 pt bold
    for cell_index in PDM_BODY_CELLS:
        table = set_hwpx_table_cell_char_pr_xml(table, cell_index, 43)  # 8 pt regular
    table = _resize_pdm_rows_xml(table)
    table = _split_pdm_table_into_pages_xml(table)
    return xml[:start] + table + xml[end:], True


def style_achievement_table_xml(xml: str) -> tuple[str, bool]:
    """Keep long achievement rows readable and allow clean page splitting."""

    target = find_hwpx_table_span_by_text(xml, ["성과지표", "기초선", "달성도"], 30)
    if target is None:
        return xml, False
    start, end, table = target
    updated = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r'\g<1>CELL', table, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\bnoAdjust=")[^"]+', r'\g<1>1', updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r'\g<1>1', updated, count=1)
    updated = updated.replace('charPrIDRef="43"', 'charPrIDRef="85"')
    updated = updated.replace('charPrIDRef="44"', 'charPrIDRef="92"')
    # The MOV guide cell has two legacy paragraphs which rHWP lays out on
    # the same baseline. A single wrapping paragraph retains all guide text.
    cells = find_hwpx_tag_spans(updated, "hp:tc")
    for index in reversed(range(len(cells))):
        start_cell, end_cell = cells[index]
        cell = updated[start_cell:end_cell]
        address = re.search(r'<hp:cellAddr\b[^>]*\browAddr="(\d+)"', cell)
        paragraphs = find_hwpx_tag_spans(cell, "hp:p")
        if address and int(address.group(1)) < ACHIEVEMENT_HEADER_ROW_COUNT and len(paragraphs) > 1:
            joined = " ".join(get_hwpx_xml_scope_text(cell[a:b]).strip() for a,b in paragraphs)
            updated, _ = set_hwpx_table_cell_text_xml(updated, index, joined)
            # set_scope_text clears additional runs but leaves empty paragraphs.
            new_cells = find_hwpx_tag_spans(updated, "hp:tc")
            a,b = new_cells[index]
            cleaned = updated[a:b]
            for pstart,pend in reversed(find_hwpx_tag_spans(cleaned, "hp:p")):
                if not get_hwpx_xml_scope_text(cleaned[pstart:pend]).strip():
                    cleaned = cleaned[:pstart] + cleaned[pend:]
            updated = updated[:a] + cleaned + updated[b:]
    updated = _set_achievement_margins_xml(updated)
    updated = _remove_empty_achievement_body_paragraphs_xml(updated)
    updated = _resize_achievement_table_rows_xml(updated)
    updated = _split_achievement_table_into_pages_xml(updated)
    return xml[:start] + updated + xml[end:], updated != table


def style_evaluation_matrix_header_xml(xml: str) -> tuple[str, bool]:
    target = find_hwpx_table_span_by_text(xml, ["분석방법", "평가질문", "적절성"], 40)
    if target is None:
        return xml, False
    start, end, table = target
    rows = find_hwpx_tag_spans(table, "hp:tr")
    if not rows:
        return xml, False
    row_start, row_end = rows[0]
    header = re.sub(
        r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+("[^>]*>)',
        r'\g<1>65\2',
        table[row_start:row_end],
    )
    updated = table[:row_start] + header + table[row_end:]
    return xml[:start] + updated + xml[end:], updated != table


def _set_matrix_cell_para_pr_xml(table_xml: str, cell_index: int, para_pr_id: int) -> str:
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


def _set_evaluation_matrix_margins_xml(table_xml: str) -> str:
    """Apply the same 1pt vertical padding policy as the grade table."""

    def set_margin(match: re.Match[str]) -> str:
        margin = match.group(0)
        for name, value in (
            ("left", EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL),
            ("right", EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL),
            ("top", EVALUATION_MATRIX_CELL_MARGIN_VERTICAL),
            ("bottom", EVALUATION_MATRIX_CELL_MARGIN_VERTICAL),
        ):
            margin = re.sub(
                rf'(\b{name}=")\d+("?)',
                rf"\g<1>{value}\2",
                margin,
                count=1,
            )
        return margin

    table_xml = re.sub(r"<hp:inMargin\b[^>]*/>", set_margin, table_xml, count=1)
    table_xml = re.sub(r"<hp:cellMargin\b[^>]*/>", set_margin, table_xml)
    return re.sub(r'(<hp:tc\b[^>]*\bhasMargin=")[01](")', r"\g<1>0\2", table_xml)


def _matrix_text_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _evaluation_matrix_cell_line_count(cell_xml: str) -> int:
    marker = "\ue000"
    marked = re.sub(r"<hp:lineBreak\s*/>", marker, cell_xml)
    text = get_hwpx_xml_scope_text(marked)
    width_match = re.search(r'<hp:cellSz\b[^>]*\bwidth="(\d+)"', cell_xml)
    width = int(width_match.group(1)) if width_match else 5000
    usable_width = max(EVALUATION_MATRIX_FONT_HEIGHT * 4, width - EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL * 2)
    chars_per_line = max(4, usable_width // EVALUATION_MATRIX_FONT_HEIGHT)
    lines = [re.sub(r"\s+", " ", part).strip() for part in text.split(marker)]
    return max(
        1,
        sum(max(1, math.ceil(_matrix_text_units(line) / chars_per_line)) for line in lines if line),
    )


def evaluation_matrix_row_height(row_xml: str, row_index: int = 1) -> int:
    """Return content-driven height with fixed 1pt top/bottom padding."""

    if row_index == 0:
        return EVALUATION_MATRIX_HEADER_ROW_HEIGHT
    line_count = 1
    for start, end in find_hwpx_tag_spans(row_xml, "hp:tc"):
        cell = row_xml[start:end]
        if not get_hwpx_xml_scope_text(cell).strip():
            continue
        line_count = max(line_count, _evaluation_matrix_cell_line_count(cell))
    return max(
        EVALUATION_MATRIX_BODY_MIN_HEIGHT,
        line_count * EVALUATION_MATRIX_LINE_HEIGHT + EVALUATION_MATRIX_CELL_MARGIN_VERTICAL * 2,
    )


def _resize_evaluation_matrix_rows_xml(table_xml: str) -> str:
    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) != 9:
        return table_xml
    rows = [table_xml[start:end] for start, end in spans]
    heights = [evaluation_matrix_row_height(row, index) for index, row in enumerate(rows)]
    for row_index, row in enumerate(rows):
        rows[row_index] = re.sub(
            r'(<hp:cellSz\b[^>]*\bheight=")\d+',
            rf"\g<1>{heights[row_index]}",
            row,
        )
    updated = table_xml[: spans[0][0]] + "".join(rows) + table_xml[spans[-1][1] :]
    return re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf"\g<1>{sum(heights)}",
        updated,
        count=1,
    )


def _normalize_evaluation_matrix_label_cells_xml(table_xml: str) -> str:
    """Remove non-visible template paragraphs from the criterion column."""

    for row_index, label in reversed(list(enumerate(EVALUATION_MATRIX_CRITERION_LABELS, start=1))):
        cells = find_hwpx_tag_spans(table_xml, "hp:tc")
        cell_index = row_index * 5
        if cell_index >= len(cells):
            continue
        start, end = cells[cell_index]
        cell = table_xml[start:end]
        sublist = re.search(r"<hp:subList\b[^>]*>", cell)
        sublist_end = cell.find("</hp:subList>")
        if not sublist or sublist_end < 0:
            continue
        canonical = (
            '<hp:p id="2147483648" paraPrIDRef="49" styleIDRef="26" '
            'pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="92"><hp:t>'
            + escape(label)
            + "</hp:t></hp:run></hp:p>"
        )
        cell = cell[: sublist.end()] + canonical + cell[sublist_end:]
        table_xml = table_xml[:start] + cell + table_xml[end:]
    return table_xml


def _split_evaluation_matrix_into_pages_xml(table_xml: str) -> str:
    """Split eight criteria into page-safe tables with repeated headers."""

    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) != 9:
        return table_xml
    prefix = table_xml[: spans[0][0]]
    suffix = table_xml[spans[-1][1] :]
    rows = [table_xml[start:end] for start, end in spans]
    base_id_match = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)
    base_id = int(base_id_match.group(1)) if base_id_match else 1330517739
    parts: list[str] = []
    for part_index, row_indexes in enumerate(EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS):
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
                rows[source_row_index],
            )
            for new_row_index, source_row_index in enumerate(row_indexes)
        ]
        part_height = sum(_physical_row_height(row) for row in selected_rows)
        part_prefix = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+',
            rf"\g<1>{part_height}",
            part_prefix,
            count=1,
        )
        parts.append(part_prefix + "".join(selected_rows) + suffix)

    page_break = (
        "</hp:run></hp:p>"
        '<hp:p id="2147483648" paraPrIDRef="64" styleIDRef="25" '
        'pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="62">'
    )
    return page_break.join(parts)


def style_evaluation_matrix_table_xml(xml: str) -> tuple[str, bool]:
    """Make the evaluation matrix multi-page and protect every wrapped line."""

    target = find_hwpx_table_span_by_text(xml, ["분석방법", "평가질문", "적절성"], 40)
    if target is None:
        return xml, False
    start, end, table = target
    updated = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r"\g<1>CELL", table, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\bnoAdjust=")[^"]+', r"\g<1>1", updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r"\g<1>1", updated, count=1)
    updated = _set_evaluation_matrix_margins_xml(updated)
    updated = _normalize_evaluation_matrix_label_cells_xml(updated)
    cells = find_hwpx_tag_spans(updated, "hp:tc")
    for cell_index in range(len(cells)):
        updated = set_hwpx_table_cell_char_pr_xml(updated, cell_index, 65 if cell_index < 5 else 92)
        if cell_index >= 5 and cell_index % 5:
            updated = _set_matrix_cell_para_pr_xml(updated, cell_index, 39)
    updated = _resize_evaluation_matrix_rows_xml(updated)
    updated = _split_evaluation_matrix_into_pages_xml(updated)
    return xml[:start] + updated + xml[end:], updated != table


def refresh_evaluation_matrix_split_heights_xml(xml: str) -> tuple[str, int]:
    """Recalculate split-table heights after final text cleanup.

    Source/citation cleanup runs after the main layout pass and can shorten
    matrix cells.  Recomputing here keeps the declared row heights aligned
    with the exact text that is finally packaged.
    """

    targets = []
    for start, end in find_hwpx_tag_spans(xml, "hp:tbl"):
        table = xml[start:end]
        if all(
            token in get_hwpx_xml_scope_text(table)
            for token in ("평가기준", "평가질문", "분석방법")
        ):
            targets.append((start, end, table))
    refreshed = 0
    for start, end, table in reversed(targets):
        row_spans = find_hwpx_tag_spans(table, "hp:tr")
        # The page-balanced profile uses five criteria on the first page and
        # three on the second so the first table no longer leaves a large
        # unused lower half. Keep compatibility with shorter matrices.
        if len(row_spans) not in {2, 3, 4, 5, 6}:
            continue
        rows = [table[row_start:row_end] for row_start, row_end in row_spans]
        heights = [evaluation_matrix_row_height(row, index) for index, row in enumerate(rows)]
        for row_index, row in enumerate(rows):
            rows[row_index] = re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf"\g<1>{heights[row_index]}",
                row,
            )
        updated = table[: row_spans[0][0]] + "".join(rows) + table[row_spans[-1][1] :]
        updated = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+',
            rf"\g<1>{sum(heights)}",
            updated,
            count=1,
        )
        xml = xml[:start] + updated + xml[end:]
        refreshed += 1
    return xml, refreshed


def style_evaluation_matrix_heading_spacing_xml(xml: str) -> tuple[str, bool]:
    """Start the matrix on a fresh page with one section-heading top gap."""

    changed = False
    for start, end in reversed(find_hwpx_tag_spans(xml, "hp:p")):
        paragraph = xml[start:end]
        if "<hp:tbl" in paragraph:
            continue
        text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip()
        if text not in {"2. 평가매트릭스", "2. 평가매트릭스(Evaluation Matrix)"}:
            continue
        updated = re.sub(
            r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
            r"\g<1>31\2",
            paragraph,
            count=1,
        )
        if re.search(r'\bpageBreak="[01]"', updated):
            updated = re.sub(r'(\bpageBreak=")[01](")', r"\g<1>1\2", updated, count=1)
        else:
            updated = re.sub(r'(<hp:p\b[^>]*)(>)', r'\1 pageBreak="1"\2', updated, count=1)
        if updated != paragraph:
            xml = xml[:start] + updated + xml[end:]
            changed = True
    return xml, changed


def detach_evaluation_matrix_table_xml(xml: str) -> tuple[str, bool]:
    """Move the matrix table out of its heading run for independent reflow."""

    heading_pos = xml.find("평가매트릭스(Evaluation Matrix)")
    if heading_pos < 0:
        return xml, False
    paragraph_start = xml.rfind("<hp:p", 0, heading_pos)
    table_start = xml.find("<hp:tbl", heading_pos)
    if paragraph_start < 0 or table_start < 0:
        return xml, False
    table_end = xml.find("</hp:tbl>", table_start)
    if table_end < 0:
        return xml, False
    table_end += len("</hp:tbl>")
    run_start = xml.rfind("<hp:run", paragraph_start, table_start)
    run_end = xml.find("</hp:run>", table_end)
    if run_start < 0 or run_end < 0:
        return xml, False
    run_end += len("</hp:run>")
    paragraph_end = xml.find("</hp:p>", run_end)
    if paragraph_end < 0:
        return xml, False
    paragraph_end += len("</hp:p>")

    before_table = xml[paragraph_start:run_start]
    before_table = re.sub(
        r'<hp:run\b[^>]*>\s*<hp:t\b[^>]*>\s*<hp:lineBreak\s*/>\s*</hp:t>\s*</hp:run>\s*$',
        "",
        before_table,
    )
    heading_paragraph = before_table + xml[run_end:paragraph_end]
    table_run = xml[run_start:run_end]
    table_paragraph = (
        '<hp:p id="2147483648" paraPrIDRef="15" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">'
        f"{table_run}</hp:p>"
    )
    return xml[:paragraph_start] + heading_paragraph + table_paragraph + xml[paragraph_end:], True
