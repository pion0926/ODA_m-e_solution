from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


PDM_SLOT_KEYS = (
    "impact_summary",
    "impact_indicator",
    "impact_mov",
    "impact_assumption",
    "outcome_summary",
    "outcome_indicator",
    "outcome_mov",
    "outcome_assumption",
    "outputs_summary",
    "outputs_indicator",
    "outputs_mov",
    "outputs_assumption",
    "activities",
    "inputs",
    "preconditions",
)

_ROW_HEADINGS = ("Impacts", "Outcomes", "Outputs", "Activities")
_LIST_START = re.compile(
    r"^(?:[-•ㅇ]\s*|\d+(?:[.-]\d+)*(?:-\d+)*(?:\.)?\s+)"
)


def _transform_point(x: float, y: float, matrix: list[float]) -> tuple[float, float]:
    return (
        (x * float(matrix[0])) + (y * float(matrix[2])) + float(matrix[4]),
        (x * float(matrix[1])) + (y * float(matrix[3])) + float(matrix[5]),
    )


def _cluster_coordinates(values: Iterable[float], tolerance: float = 2.0) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or abs(value - (sum(clusters[-1]) / len(clusters[-1]))) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _semantic_cell_text(fragments: list[tuple[float, float, str]]) -> str:
    """Join PDF visual lines while retaining logical list-item boundaries."""
    if not fragments:
        return ""
    line_groups: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, text in sorted(fragments, key=lambda item: (-item[0], item[1])):
        if not line_groups or abs(y - line_groups[-1][0]) > 0.8:
            line_groups.append((y, [(x, text)]))
        else:
            line_groups[-1][1].append((x, text))

    visual_lines: list[str] = []
    for _baseline, pieces in line_groups:
        value = "".join(text for _x, text in sorted(pieces, key=lambda item: item[0]))
        value = re.sub(r"[ \t]+", " ", value).strip()
        if value:
            visual_lines.append(value)

    logical_lines: list[str] = []
    for line in visual_lines:
        if not logical_lines or _LIST_START.match(line):
            logical_lines.append(line)
        else:
            logical_lines[-1] = (logical_lines[-1].rstrip() + " " + line.lstrip()).strip()
    return "\n".join(logical_lines).strip()


def _remove_heading(text: str, heading: str) -> str:
    patterns = {
        "Impacts": r"^\s*Impacts\s*(?:\(\s*영향\s*\))?\s*",
        "Outcomes": r"^\s*Outcomes\s*(?:\(\s*성과\s*\))?\s*",
        "Outputs": r"^\s*Outputs\s*(?:\(\s*산출물\s*\))?\s*",
        "Activities": r"^\s*Activities\s*(?:\(\s*활동\s*\))?\s*",
        "Inputs": r"^\s*Inputs\s*(?:\(\s*투입물?\s*\))?\s*",
        "Pre-conditions": r"^\s*Pre-conditions\s*(?:\(\s*(?:선행|전제)조건\s*\))?\s*",
    }
    return re.sub(patterns[heading], "", text, count=1, flags=re.IGNORECASE).strip()


def _page_pdm_slots(page) -> dict[str, str]:
    fragments: list[tuple[float, float, str]] = []
    segments: list[tuple[float, float, float, float]] = []
    pen: tuple[float, float] | None = None

    def visit_text(text, cm, tm, _font, _size) -> None:
        if not str(text).strip() or (float(tm[4]) == 0 and float(tm[5]) == 0):
            return
        x, y = _transform_point(float(tm[4]), float(tm[5]), cm)
        fragments.append((y, x, str(text)))

    def visit_operand(op, args, cm, _tm) -> None:
        nonlocal pen
        if op == b"m" and len(args) >= 2:
            pen = _transform_point(float(args[0]), float(args[1]), cm)
        elif op == b"l" and len(args) >= 2 and pen is not None:
            endpoint = _transform_point(float(args[0]), float(args[1]), cm)
            segments.append((pen[0], pen[1], endpoint[0], endpoint[1]))
            pen = endpoint

    page.extract_text(visitor_text=visit_text, visitor_operand_before=visit_operand)
    page_text = " ".join(item[2] for item in fragments)
    if not all(label in page_text for label in _ROW_HEADINGS):
        return {}

    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    vertical_values = [
        (x1 + x2) / 2
        for x1, y1, x2, y2 in segments
        if abs(x1 - x2) <= 0.8
        and abs(y2 - y1) >= height * 0.35
        and width * 0.04 < x1 < width * 0.96
    ]
    horizontal_segments = [
        ((y1 + y2) / 2, min(x1, x2), max(x1, x2))
        for x1, y1, x2, y2 in segments
        if abs(y1 - y2) <= 0.8
        and abs(x2 - x1) >= width * 0.12
        and height * 0.03 < y1 < height * 0.97
    ]
    verticals = _cluster_coordinates(vertical_values)
    horizontal_clusters: list[list[tuple[float, float, float]]] = []
    for segment in sorted(horizontal_segments):
        if (
            not horizontal_clusters
            or abs(segment[0] - sum(item[0] for item in horizontal_clusters[-1]) / len(horizontal_clusters[-1])) > 2.0
        ):
            horizontal_clusters.append([segment])
        else:
            horizontal_clusters[-1].append(segment)
    horizontals = [
        sum(item[0] for item in cluster) / len(cluster)
        for cluster in horizontal_clusters
        if max(item[2] for item in cluster) - min(item[1] for item in cluster) >= width * 0.55
    ]

    heading_points: dict[str, tuple[float, float]] = {}
    for y, x, text in fragments:
        stripped = text.strip()
        if stripped in _ROW_HEADINGS and stripped not in heading_points:
            heading_points[stripped] = (x, y)
    if len(heading_points) != 4:
        return {}

    impact_x, impact_y = heading_points["Impacts"]
    left_candidates = [value for value in verticals if value <= impact_x + 2.5]
    if not left_candidates:
        return {}
    left = max(left_candidates)
    columns = [value for value in verticals if value >= left - 1.0]
    if len(columns) < 5:
        return {}
    columns = columns[:5]

    row_tops: list[float] = []
    for heading in _ROW_HEADINGS:
        heading_y = heading_points[heading][1]
        candidates = [value for value in horizontals if value > heading_y]
        if not candidates:
            return {}
        row_tops.append(min(candidates))
    if not all(row_tops[index] > row_tops[index + 1] for index in range(3)):
        return {}
    header_candidates = [value for value in horizontals if value > row_tops[0] + 1.0]
    bottom_candidates = [value for value in horizontals if value < row_tops[-1] - 1.0]
    if not header_candidates or not bottom_candidates:
        return {}
    row_bounds = [min(header_candidates), *row_tops, min(bottom_candidates)]

    cells: dict[tuple[int, int], list[tuple[float, float, str]]] = defaultdict(list)
    for y, x, text in fragments:
        row_index = next(
            (
                index
                for index in range(4)
                if row_bounds[index + 1] > y > row_bounds[index + 2]
            ),
            -1,
        )
        if row_index < 0:
            continue
        if row_index == 3 and columns[1] <= x < columns[3]:
            column_index = 1
        else:
            column_index = next(
                (
                    index
                    for index in range(4)
                    if columns[index] <= x < columns[index + 1]
                ),
                -1,
            )
        if column_index >= 0:
            cells[(row_index, column_index)].append((y, x, text))

    row_names = ("Impacts", "Outcomes", "Outputs")
    row_slot_prefixes = ("impact", "outcome", "outputs")
    result: dict[str, str] = {}
    for row_index, (heading, prefix) in enumerate(zip(row_names, row_slot_prefixes)):
        result[f"{prefix}_summary"] = _remove_heading(
            _semantic_cell_text(cells[(row_index, 0)]), heading
        )
        result[f"{prefix}_indicator"] = _semantic_cell_text(cells[(row_index, 1)])
        result[f"{prefix}_mov"] = _semantic_cell_text(cells[(row_index, 2)])
        result[f"{prefix}_assumption"] = _semantic_cell_text(cells[(row_index, 3)])

    result["activities"] = _remove_heading(
        _semantic_cell_text(cells[(3, 0)]), "Activities"
    )
    result["inputs"] = _remove_heading(
        _semantic_cell_text(cells[(3, 1)]), "Inputs"
    )
    result["preconditions"] = _remove_heading(
        _semantic_cell_text(cells[(3, 3)]), "Pre-conditions"
    )
    if not all(result.get(key) for key in PDM_SLOT_KEYS):
        return {}
    return result


def extract_authoritative_pdm_slots(pdf_path: str | Path) -> dict[str, str]:
    """Extract the 15 PDM cells from the uploaded source table without rewriting."""
    path = Path(pdf_path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return {}
    try:
        reader = PdfReader(str(path))
        for page in reader.pages:
            slots = _page_pdm_slots(page)
            if slots:
                return slots
    except Exception:
        return {}
    return {}
