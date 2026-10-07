from __future__ import annotations

import math
import re

from backend.oda_me.hwpx.patchers import (
    find_hwpx_tag_spans,
    find_hwpx_table_span_by_text,
    get_hwpx_xml_scope_text,
)

from ..quality_profile import layout_profile
from .overflow import fit_table_details, append_table_details, oversized_group_cells


_PROFILE = layout_profile("recommendation_tables")
FONT_HEIGHT = int(_PROFILE["font_height"])
LINE_SPACING_PERCENT = int(_PROFILE["line_spacing_percent"])
LINE_HEIGHT = FONT_HEIGHT * LINE_SPACING_PERCENT // 100
MARGIN_HORIZONTAL = int(_PROFILE["cell_margin_horizontal"])
MARGIN_VERTICAL = int(_PROFILE["cell_margin_vertical"])
FEEDBACK_ROWS_PER_PAGE = int(_PROFILE["feedback_rows_per_page"])
LESSONS_ROWS_PER_PAGE = int(_PROFILE["lessons_rows_per_page"])
LESSONS_MAX_TABLE_HEIGHT = int(_PROFILE["lessons_max_table_height"])


def recommendation_page_budget(xml: str, configured: int | None = None) -> int:
    """Reserve the visible section/subsection headings above a landscape table."""
    budget = configured or 60000
    page = re.search(r'<hp:pagePr\b([^>]*)>', xml)
    margin = re.search(r'<hp:margin\b([^>]*)/?>', xml)
    if not page or not margin:
        return budget
    page_values = dict(re.findall(r'(\w+)="([^"]*)"', page[1]))
    margins = dict(re.findall(r'(\w+)="(\d+)"', margin[1]))
    width, height = int(page_values.get('width', 0)), int(page_values.get('height', 0))
    if not width or not height:
        return budget
    physical_height = min(width, height) if page_values.get('landscape') == 'NARROWLY' else max(width, height)
    available = physical_height - sum(int(margins.get(k, 0)) for k in ('top', 'bottom', 'header', 'footer'))
    # Two visible headings plus their paragraph spacing must remain on the
    # first table page. A portrait-only 60000 budget orphaned those headings.
    return min(budget, max(3000, available - 6000))


def _text_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _cell_line_count(cell_xml: str) -> int:
    marker = "\ue000"
    marked = re.sub(r"<hp:lineBreak\s*/>", marker, cell_xml)
    text = get_hwpx_xml_scope_text(marked)
    width_match = re.search(r'<hp:cellSz\b[^>]*\bwidth="(\d+)"', cell_xml)
    width = int(width_match.group(1)) if width_match else 9000
    chars_per_line = max(4, (width - MARGIN_HORIZONTAL * 2) // FONT_HEIGHT)
    lines = [re.sub(r"\s+", " ", item).strip() for item in text.split(marker)]
    return max(
        1,
        sum(max(1, math.ceil(_text_units(line) / chars_per_line)) for line in lines if line),
    )


def _row_height(row_xml: str, *, header: bool) -> int:
    if header:
        heights = [
            int(value)
            for value in re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row_xml)
        ]
        return max(1500, min(heights) if heights else 1500)
    line_count = max(
        (_cell_line_count(row_xml[start:end]) for start, end in find_hwpx_tag_spans(row_xml, "hp:tc")),
        default=1,
    )
    return max(3200, line_count * LINE_HEIGHT + MARGIN_VERTICAL * 2)


def _style_rows_xml(table_xml: str, header_rows: int) -> str:
    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    rows = [table_xml[start:end] for start, end in spans]
    heights: list[int] = []
    for row_index, row in enumerate(rows):
        header = row_index < header_rows
        char_pr_id = 65 if header else 92
        row = re.sub(
            r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+',
            rf'\g<1>{char_pr_id}',
            row,
        )
        row = re.sub(
            r'<hp:cellMargin\b[^>]*/>',
            (
                f'<hp:cellMargin left="{MARGIN_HORIZONTAL}" right="{MARGIN_HORIZONTAL}" '
                f'top="{MARGIN_VERTICAL}" bottom="{MARGIN_VERTICAL}"/>'
            ),
            row,
        )
        height = _row_height(row, header=header)
        if not header:
            row = re.sub(
                r'(<hp:cellSz\b[^>]*\bheight=")\d+',
                rf'\g<1>{height}',
                row,
            )
        rows[row_index] = row
        heights.append(height)
    updated = table_xml[: spans[0][0]] + "".join(rows) + table_xml[spans[-1][1] :]
    updated = re.sub(
        r'(<hp:sz\b[^>]*\bheight=")\d+',
        rf'\g<1>{sum(heights)}',
        updated,
        count=1,
    )
    updated = re.sub(r'(<hp:tbl\b[^>]*\bpageBreak=")[^"]+', r'\g<1>CELL', updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\bnoAdjust=")[^"]+', r'\g<1>1', updated, count=1)
    updated = re.sub(r'(<hp:tbl\b[^>]*\brepeatHeader=")[^"]+', r'\g<1>1', updated, count=1)
    updated = re.sub(
        r'<hp:inMargin\b[^>]*/>',
        (
            f'<hp:inMargin left="{MARGIN_HORIZONTAL}" right="{MARGIN_HORIZONTAL}" '
            f'top="{MARGIN_VERTICAL}" bottom="{MARGIN_VERTICAL}"/>'
        ),
        updated,
        count=1,
    )
    return updated


def _split_table_xml(
    table_xml: str,
    *,
    header_rows: int,
    rows_per_page: int,
    max_table_height: int | None = None,
) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if len(spans) <= header_rows:
        return table_xml, 1
    rows = [table_xml[start:end] for start, end in spans]
    prefix = table_xml[: spans[0][0]]
    suffix = table_xml[spans[-1][1] :]
    base_id_match = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', prefix)
    base_id = int(base_id_match.group(1)) if base_id_match else 1830000000
    header_height = sum(_row_height(row, header=True) for row in rows[:header_rows])
    groups: list[list[int]] = []
    current_group: list[int] = []
    current_height = header_height
    for body_index in range(header_rows, len(rows)):
        body_height = _row_height(rows[body_index], header=False)
        exceeds_row_limit = len(current_group) >= rows_per_page
        exceeds_height = bool(
            max_table_height
            and current_group
            and current_height + body_height > max_table_height
        )
        if exceeds_row_limit or exceeds_height:
            groups.append(current_group)
            current_group = []
            current_height = header_height
        current_group.append(body_index)
        current_height += body_height
    if current_group:
        groups.append(current_group)
    parts: list[str] = []
    for part_index, body_group in enumerate(groups):
        row_indexes = list(range(header_rows)) + body_group
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
        part_height = sum(
            _row_height(row, header=index < header_rows)
            for index, row in enumerate(selected_rows)
        )
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
    return page_break.join(parts), len(parts)


def style_recommendation_tables_xml(xml: str) -> tuple[str, dict[str, int | bool]]:
    checks: dict[str, int | bool] = {
        "feedback_table_pages": 0,
        "lessons_table_pages": 0,
        "recommendation_full_text": True,
    }
    targets = (
        ("feedback", ["환류과제", "이행부서"], 1, FEEDBACK_ROWS_PER_PAGE, None),
        (
            "lessons",
            ["평가 교훈 분석", "체크리스트"],
            2,
            LESSONS_ROWS_PER_PAGE,
            LESSONS_MAX_TABLE_HEIGHT,
        ),
    )
    for name, needles, header_rows, rows_per_page, max_table_height in targets:
        target = find_hwpx_table_span_by_text(xml, needles, 10)
        if target is None:
            checks[f"{name}_table_pages"] = 0
            continue
        start, end, table = target
        row_count = len(find_hwpx_tag_spans(table, 'hp:tr'))
        budget = recommendation_page_budget(xml, max_table_height)
        groups = [tuple(range(header_rows)) + (i,) for i in range(header_rows, row_count)]
        table, details = fit_table_details(table, lambda value: oversized_group_cells(
            _style_rows_xml(value, header_rows), groups, budget), '환류과제' if name == 'feedback' else '교훈')
        updated = _style_rows_xml(table, header_rows)
        updated, pages = _split_table_xml(
            updated,
            header_rows=header_rows,
            rows_per_page=rows_per_page,
            max_table_height=budget,
        )
        updated = append_table_details(updated, details)
        if "…" in get_hwpx_xml_scope_text(updated):
            checks["recommendation_full_text"] = False
        xml = xml[:start] + updated + xml[end:]
        checks[f"{name}_table_pages"] = pages
    return xml, checks
