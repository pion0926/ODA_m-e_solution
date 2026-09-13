from __future__ import annotations

import re
from html import escape

from ..quality_profile import layout_profile
from .control_integrity import remove_empty_controls_xml


_PROFILE = layout_profile("page_identity")
IDENTITY_ENABLED = bool(_PROFILE.get("enabled", True))
PAGE_NUMBER_POSITION = str(_PROFILE["page_number_position"])
PAGE_NUMBER_SIDE_CHARACTER = str(_PROFILE["page_number_side_character"])
APPLY_FROM_SECTION = int(_PROFILE["apply_from_section"])
HEADER_MAX_CHARACTERS = int(_PROFILE["header_max_characters"])
HEADER_TEXT = str(_PROFILE.get("header_text") or "").strip()
HEADER_PARAGRAPH_PROPERTY_ID = int(_PROFILE.get("header_paragraph_property_id") or 1)
FOOTER_PARAGRAPH_PROPERTY_ID = int(_PROFILE.get("footer_paragraph_property_id") or 25)
HEADER_RESERVE_HEIGHT = int(_PROFILE.get("header_reserve_height") or 2500)
HEADER_TEXT_HEIGHT = int(_PROFILE.get("header_text_height") or 1500)
HEADER_BODY_GAP = int(_PROFILE.get("header_body_gap") or 700)
IDENTITY_REMOVE_TEXTS = tuple(
    str(value).strip()
    for value in (_PROFILE.get("remove_texts") or (HEADER_TEXT,))
    if str(value).strip()
)


def _section_index(section_path: str) -> int:
    match = re.search(r"section(\d+)\.xml$", section_path)
    return int(match.group(1)) if match else -1


def _short_report_header(project: dict | None) -> str:
    if HEADER_TEXT:
        return HEADER_TEXT
    title = re.sub(r"\s+", " ", str((project or {}).get("title") or "ODA 평가사업")).strip()
    suffix = " · 현재시점 문헌기반 평가보고서"
    budget = max(12, HEADER_MAX_CHARACTERS - len(suffix))
    if len(title) > budget:
        title = title[: max(1, budget - 1)].rstrip() + "…"
    return title + suffix


def _populate_empty_headers_xml(xml: str, header_text: str) -> tuple[str, int]:
    changed = 0

    def replace_header(match: re.Match[str]) -> str:
        nonlocal changed
        header = match.group(0)
        if re.sub(r"<[^>]+>", "", header).strip():
            return header
        updated, count = re.subn(
            r'<hp:run\b([^>]*)\bcharPrIDRef="14"([^>]*)/>',
            rf'<hp:run\1charPrIDRef="14"\2><hp:t>{escape(header_text)}</hp:t></hp:run>',
            header,
            count=1,
        )
        if count:
            updated = re.sub(
                r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
                rf'\g<1>{HEADER_PARAGRAPH_PROPERTY_ID}\2',
                updated,
                count=1,
            )
        changed += int(count > 0)
        return updated

    return re.sub(r"<hp:header\b.*?</hp:header>", replace_header, xml, flags=re.DOTALL), changed


def _separate_header_from_body_xml(xml: str) -> tuple[str, int]:
    """Reserve a one-line header band before the body starts.

    HWPX stores the reserved band in ``hp:margin@header`` and the header
    layout box height in ``hp:header/hp:subList@textHeight``. Adjusting only
    one of them can still let a tall template box overlap the first body line,
    so both values are normalized from the editable quality profile.
    """

    changed = 0

    def replace_margin(match: re.Match[str]) -> str:
        nonlocal changed
        opening = match.group(0)
        header_match = re.search(r'\bheader="(\d+)"', opening)
        if not header_match:
            return opening
        # rHWP lays out the body at ``top + header``. The header value is a
        # reserved band, not an absolute paper offset. Keep enough room for
        # one normalized header line and an explicit body gap.
        target = max(HEADER_RESERVE_HEIGHT, HEADER_TEXT_HEIGHT + HEADER_BODY_GAP)
        updated = re.sub(r'(\bheader=")\d+(")', rf'\g<1>{target}\2', opening, count=1)
        changed += int(updated != opening)
        return updated

    updated = re.sub(r"<hp:margin\b[^>]*/>", replace_margin, xml)

    def replace_header_box(match: re.Match[str]) -> str:
        nonlocal changed
        header = match.group(0)
        resized = re.sub(
            r'(<hp:subList\b[^>]*\btextHeight=")\d+(")',
            rf'\g<1>{HEADER_TEXT_HEIGHT}\2',
            header,
            count=1,
        )
        changed += int(resized != header)
        return resized

    updated = re.sub(r"<hp:header\b.*?</hp:header>", replace_header_box, updated, flags=re.DOTALL)
    return updated, changed


def _move_identity_to_footer_xml(xml: str) -> tuple[str, int]:
    """Move the repeated identity out of the body-first-line render band.

    rHWP renders template header controls on the same baseline as the first
    body line on continuation pages. Reusing the controls as left-aligned
    footers keeps the document identity visible without covering report text.
    """

    changed = 0

    def replace_control(match: re.Match[str]) -> str:
        nonlocal changed
        control = match.group(0)
        updated = control.replace("<hp:header", "<hp:footer", 1).replace(
            "</hp:header>", "</hp:footer>", 1
        )
        updated = re.sub(
            r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
            rf'\g<1>{FOOTER_PARAGRAPH_PROPERTY_ID}\2',
            updated,
            count=1,
        )
        changed += int(updated != control)
        return updated

    return re.sub(r"<hp:header\b.*?</hp:header>", replace_control, xml, flags=re.DOTALL), changed


def _remove_identity_controls_xml(xml: str) -> tuple[str, int]:
    """Remove the legacy repeated brand mark without touching page numbers.

    The source template has one empty header control.  Earlier exports filled
    that control with ``K-ODAME`` and converted it to a footer, which made the
    mark repeat on every following page.  When the editable profile disables
    the identity mark, both the empty template control and any legacy control
    containing the configured mark are removed.  ``hp:pageNum`` remains an
    independent section control and is intentionally preserved.
    """

    removed = 0

    def replace_control(match: re.Match[str]) -> str:
        nonlocal removed
        control = match.group(0)
        visible = re.sub(r"<[^>]+>", "", control)
        visible = re.sub(r"\s+", " ", visible).strip()
        if not visible or any(text in visible for text in IDENTITY_REMOVE_TEXTS):
            removed += 1
            return ""
        return control

    updated = re.sub(
        r"<hp:(?P<kind>header|footer)\b.*?</hp:(?P=kind)>",
        replace_control,
        xml,
        flags=re.DOTALL,
    )
    # Removing the header/footer must not leave a childless control wrapper.
    updated, _ = remove_empty_controls_xml(updated)
    return updated, removed


def apply_page_identity_xml(
    section_path: str,
    xml: str,
    project: dict | None = None,
) -> tuple[str, dict[str, int | bool]]:
    """Activate printed page numbers and reuse the template header controls."""

    section_index = _section_index(section_path)
    checks: dict[str, int | bool] = {
        "page_number_activated": False,
        "headers_populated": 0,
        "identity_controls_removed": 0,
    }
    if section_index < APPLY_FROM_SECTION:
        return xml, checks

    page_num = (
        f'<hp:pageNum pos="{PAGE_NUMBER_POSITION}" formatType="DIGIT" '
        f'sideChar="{escape(PAGE_NUMBER_SIDE_CHARACTER)}"/>'
    )
    updated, count = re.subn(r'<hp:pageNum\b[^>]*/>', page_num, xml)
    if count == 0:
        # ``secPr`` may itself contain header/footer runs.  A single regex
        # that starts at ``hp:run`` can therefore bind to an inner run and
        # miss the enclosing section-property run.  Locate the section
        # property first, then its actual outer run boundaries.
        sec_start = updated.find("<hp:secPr")
        sec_close = updated.find("</hp:secPr>", sec_start) if sec_start >= 0 else -1
        if sec_start >= 0 and sec_close >= 0:
            run_open = updated.rfind("<hp:run", 0, sec_start)
            run_open_end = updated.find(">", run_open) if run_open >= 0 else -1
            run_close = updated.find("</hp:run>", sec_close + len("</hp:secPr>"))
            opening = updated[run_open : run_open_end + 1] if run_open_end >= 0 else ""
            char_match = re.search(r'\bcharPrIDRef="(?P<char>\d+)"', opening)
            if char_match and run_close >= 0:
                insertion_point = run_close + len("</hp:run>")
                control_run = (
                    f'<hp:run charPrIDRef="{char_match.group("char")}">'
                    f'<hp:ctrl>{page_num}</hp:ctrl></hp:run>'
                )
                updated = updated[:insertion_point] + control_run + updated[insertion_point:]
                count = 1
    xml = updated
    checks["page_number_activated"] = count > 0
    if not IDENTITY_ENABLED:
        xml, removed = _remove_identity_controls_xml(xml)
        checks["identity_controls_removed"] = removed
        checks["identity_mark_disabled"] = True
        return xml, checks
    if "<hp:header" in xml:
        xml, header_count = _populate_empty_headers_xml(xml, _short_report_header(project))
        checks["headers_populated"] = header_count
        xml, margin_count = _separate_header_from_body_xml(xml)
        checks["header_margin_adjusted"] = margin_count > 0
        xml, footer_count = _move_identity_to_footer_xml(xml)
        checks["identity_footers_created"] = footer_count
    return xml, checks
