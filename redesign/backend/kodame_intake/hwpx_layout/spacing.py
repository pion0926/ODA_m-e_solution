from __future__ import annotations

import binascii
import re

from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans, get_hwpx_xml_scope_text


# Keep this aligned with the report heading roles that are configured with
# keep-with-next pagination in ``headings.py``.
REPORT_HEADING_PARA_IDS = frozenset({"15", "31", "67", "69"})

EVALUATION_OVERVIEW_CHAPTER_HEADING = "III. 평가개요"


def _visible_text(paragraph_xml: str) -> str:
    return re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph_xml)).strip()


def _top_level_paragraphs(xml: str) -> list[tuple[int, int, str]]:
    table_spans = find_hwpx_tag_spans(xml, "hp:tbl")
    return [
        (start, end, xml[start:end])
        for start, end in find_hwpx_tag_spans(xml, "hp:p")
        if not any(table_start < start and end < table_end for table_start, table_end in table_spans)
    ]


def _blank_paragraph_xml(heading: str) -> str:
    paragraph_id = binascii.crc32(f"heading-gap|{heading}".encode("utf-8")) & 0xFFFFFFFF
    return (
        f'<hp:p id="{paragraph_id}" paraPrIDRef="71" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="28"><hp:t xml:space="preserve"> </hp:t></hp:run>'
        "</hp:p>"
    )


def _paragraph_para_pr_id(paragraph_xml: str) -> str:
    opening = re.match(r"<hp:p\b[^>]*>", paragraph_xml)
    if not opening:
        return ""
    match = re.search(r'\bparaPrIDRef="(\d+)"', opening.group(0))
    return match.group(1) if match else ""


def _starts_on_fresh_page(paragraph_xml: str) -> bool:
    opening = re.match(r"<hp:p\b[^>]*>", paragraph_xml)
    return bool(opening and 'pageBreak="1"' in opening.group(0))


def _is_report_heading(paragraph_xml: str) -> bool:
    return bool(
        _visible_text(paragraph_xml)
        and _paragraph_para_pr_id(paragraph_xml) in REPORT_HEADING_PARA_IDS
    )


def ensure_blank_line_before_report_headings_xml(xml: str) -> tuple[str, int]:
    """Insert one blank line before every in-flow report heading.

    Report headings are identified by their paragraph role rather than by a
    hard-coded text list.  A heading that already starts a fresh page does not
    need a preceding spacer, and an existing empty paragraph is preserved as
    the single spacer instead of adding a duplicate.
    """

    paragraphs = _top_level_paragraphs(xml)
    insertions: list[tuple[int, str]] = []
    for index, (start, _end, paragraph) in enumerate(paragraphs):
        if index == 0 or not _is_report_heading(paragraph):
            continue
        if _starts_on_fresh_page(paragraph):
            continue
        if _visible_text(paragraphs[index - 1][2]):
            insertions.append((start, _blank_paragraph_xml(_visible_text(paragraph))))
    for start, blank in reversed(insertions):
        xml = xml[:start] + blank + xml[start:]
    return xml, len(insertions)


def report_heading_gap_violations_xml(xml: str) -> list[str]:
    """Return in-flow report headings that still touch preceding body text."""

    paragraphs = _top_level_paragraphs(xml)
    violations: list[str] = []
    for index, (_start, _end, paragraph) in enumerate(paragraphs):
        if index == 0 or not _is_report_heading(paragraph):
            continue
        if _starts_on_fresh_page(paragraph):
            continue
        if _visible_text(paragraphs[index - 1][2]):
            violations.append(_visible_text(paragraph))
    return violations


def ensure_blank_line_before_headings_xml(
    xml: str,
    headings: frozenset[str] | set[str],
) -> tuple[str, int]:
    """Insert exactly one visible blank report line before selected headings."""

    paragraphs = _top_level_paragraphs(xml)
    insertions: list[tuple[int, str]] = []
    for index, (start, _end, paragraph) in enumerate(paragraphs):
        heading = _visible_text(paragraph)
        if heading not in headings:
            continue
        previous_text = _visible_text(paragraphs[index - 1][2]) if index else ""
        if previous_text:
            insertions.append((start, _blank_paragraph_xml(heading)))
    for start, blank in reversed(insertions):
        xml = xml[:start] + blank + xml[start:]
    return xml, len(insertions)


def heading_has_blank_line_before_xml(xml: str, heading: str) -> bool:
    paragraphs = _top_level_paragraphs(xml)
    for index, (_start, _end, paragraph) in enumerate(paragraphs):
        if _visible_text(paragraph) != heading:
            continue
        return index > 0 and not _visible_text(paragraphs[index - 1][2])
    return False


def ensure_page_break_before_heading_xml(xml: str, heading: str) -> tuple[str, bool]:
    """Keep a major chapter heading from being orphaned below the preceding table."""

    for start, end, paragraph in _top_level_paragraphs(xml):
        if _visible_text(paragraph) != heading:
            continue
        opening = re.match(r"<hp:p\b[^>]*>", paragraph)
        if not opening:
            return xml, False
        updated_opening = re.sub(
            r'\bpageBreak="[01]"',
            'pageBreak="1"',
            opening.group(0),
            count=1,
        )
        if 'pageBreak="' not in opening.group(0):
            updated_opening = updated_opening[:-1] + ' pageBreak="1">'
        if updated_opening == opening.group(0):
            return xml, False
        updated_paragraph = updated_opening + paragraph[opening.end():]
        return xml[:start] + updated_paragraph + xml[end:], True
    return xml, False


def heading_starts_on_fresh_page_xml(xml: str, heading: str) -> bool:
    for _start, _end, paragraph in _top_level_paragraphs(xml):
        if _visible_text(paragraph) != heading:
            continue
        opening = re.match(r"<hp:p\b[^>]*>", paragraph)
        return bool(opening and 'pageBreak="1"' in opening.group(0))
    return False
