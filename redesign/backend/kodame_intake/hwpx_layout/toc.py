from __future__ import annotations

import re
import zipfile
from io import BytesIO

from backend.oda_me.hwpx.patchers import (
    TOC_SECTION2_LABELS,
    _toc_labeled_numeric_target,
    find_hwpx_all_tag_spans,
    get_hwpx_xml_scope_text,
    patch_hwpx_section2_toc_page_numbers_xml,
    repack_hwpx_preserving_original_entries,
)


ACHIEVEMENT_TOC_PARA_PR_ID = "40"
TOC_RIGHT_TAB_PR_ID = "3"
TOC_RIGHT_TAB_POSITION = "42520"
APPENDIX_TOC_LABELS = (
    "1. 평가결과 영문 요약",
    "2. 현지(원격) 조사개요",
    "3. 일별활동내역",
    "4. 면담자 목록",
    "5. 설문조사지",
    "6. 참고문헌 목록",
    "7. 그 외 첨부자료",
)


def _normalized_toc_label(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def prune_unexported_appendix_toc_xml(
    xml: str,
    page_numbers: dict[str, str],
) -> tuple[str, int]:
    """Remove the template-only appendix block when no appendix is exported.

    The current report pipeline creates 27 logical sections and no appendix
    pages. Keeping the sample template's appendix rows therefore produced
    dotted leaders with empty page-number slots at the end of the TOC. The
    whole block is removed as one XML range so no blank rows remain.
    """

    appendix_keys = tuple(key for key in page_numbers if key.startswith("appendix_"))
    if any(str(page_numbers.get(key) or "").strip() for key in appendix_keys):
        return xml, 0
    leaf_paragraphs: list[tuple[int, int, str]] = []
    for start, end in find_hwpx_all_tag_spans(xml, "hp:p"):
        paragraph = xml[start:end]
        if paragraph.count("<hp:p") != 1:
            continue
        text = get_hwpx_xml_scope_text(paragraph).strip()
        leaf_paragraphs.append((start, end, text))
    heading = next(
        (
            item
            for item in leaf_paragraphs
            if _normalized_toc_label(item[2]) == "첨부"
        ),
        None,
    )
    if heading is None:
        return xml, 0
    appendix_rows = [
        item
        for item in leaf_paragraphs
        if item[0] >= heading[0]
        and any(
            _normalized_toc_label(item[2]).startswith(_normalized_toc_label(label))
            for label in APPENDIX_TOC_LABELS
        )
    ]
    end = max((item[1] for item in appendix_rows), default=heading[1])
    return xml[: heading[0]] + xml[end:], 1


def patch_toc_header_layout(xml: str) -> tuple[str, bool]:
    """Attach the official right-aligned dotted tab to the IV chapter style.

    The source template gives the exceptional ``Ⅳ. 성과달성도`` paragraph
    style 40, whose tab definition is 0 (no right tab).  Adding an ``hp:tab``
    node to section1 alone therefore looks correct in XML but collapses next
    to the label in rHWP.  Style 3 already owns the reviewed 42,520 HWPUNIT
    right tab used by the neighbouring TOC rows, so only the reference is
    changed; the chapter's left margin, font and border remain untouched.
    """

    pattern = re.compile(
        rf'<hh:paraPr\b(?=[^>]*\bid="{ACHIEVEMENT_TOC_PARA_PR_ID}")'
        r'(?=[^>]*\btabPrIDRef=")[^>]*>'
    )
    match = pattern.search(xml)
    if not match:
        return xml, False
    opening = match.group(0)
    updated = re.sub(
        r'(\btabPrIDRef=")[^"]*(")',
        rf'\g<1>{TOC_RIGHT_TAB_PR_ID}\2',
        opening,
        count=1,
    )
    if updated == opening:
        return xml, False
    return xml[: match.start()] + updated + xml[match.end() :], True


def clean_toc_annotations_xml(xml: str) -> str:
    """Remove authoring-only notes without changing the fixed TOC geometry."""

    xml = re.sub(r"\s*\((?:준비도|선택)\)", "", xml)
    return xml.replace("1. 평가매트릭스(Evaluation Matrix)", "2. 평가매트릭스(Evaluation Matrix)")


def normalize_toc_page_number_spacing_xml(xml: str) -> tuple[str, int]:
    """Remove template padding around every visible TOC page number.

    Two reviewed template rows stored their page values as `` 23 `` and
    `` 41 `` while neighboring rows stored bare digits. The page updater
    previously preserved that padding, so rHWP placed those values in a
    different horizontal position even though every row shared paraPr 53 and
    the same right-tab contract. Page numbers are machine-owned values; their
    text nodes must therefore contain the exact integer and no authoring
    whitespace.
    """

    changed = 0
    for label in TOC_SECTION2_LABELS.values():
        target = _toc_labeled_numeric_target(xml, label)
        if target is None:
            continue
        start, end, paragraph, match = target
        raw_value = match.group(2)
        normalized = raw_value.strip()
        if not normalized or raw_value == normalized:
            continue
        updated = (
            paragraph[:match.start()]
            + match.group(1)
            + normalized
            + match.group(3)
            + paragraph[match.end():]
        )
        xml = xml[:start] + updated + xml[end:]
        changed += 1
    return xml, changed


def normalize_toc_tab_widths_xml(xml: str) -> tuple[str, int]:
    """Use a RIGHT inline tab consistent with the paragraph's right tab stop.

    Keep line-segment vertical geometry: the TOC lives inside a text box, and
    deleting its line caches collapses rows in rHWP. Preserve any real width:
    zeroing it made native Hangul collapse the leader. Final export replaces
    numbered rows with fixed cells, so this is only a legacy intermediate pass.
    """
    changed = 0
    for label in TOC_SECTION2_LABELS.values():
        target = _toc_labeled_numeric_target(xml, label)
        if target is None:
            continue
        start, end, paragraph, _ = target
        updated = paragraph
        def right_tab(match: re.Match[str]) -> str:
            tab = match.group(0)
            if re.search(r'\btype="', tab):
                return re.sub(r'\btype="[^"]*"', 'type="1"', tab)
            return tab.replace('/>', ' type="1"/>')
        updated = re.sub(r'<hp:tab\b[^>]*/>', right_tab, updated)
        if updated != paragraph:
            xml = xml[:start] + updated + xml[end:]
            changed += 1
    return xml, changed


def patch_toc_page_numbers(data: bytes, page_numbers: dict[str, str]) -> tuple[bytes, int]:
    """Write renderer-derived page numbers into the original fixed TOC slots."""

    output = BytesIO()
    changed = 0
    with zipfile.ZipFile(BytesIO(data), "r") as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                xml, _ = patch_toc_header_layout(raw.decode("utf-8"))
                raw = xml.encode("utf-8")
            elif info.filename == "Contents/section1.xml":
                xml, changed = patch_hwpx_section2_toc_page_numbers_xml(
                    raw.decode("utf-8"), page_numbers
                )
                xml, spacing_changed = normalize_toc_page_number_spacing_xml(xml)
                changed += spacing_changed
                xml, tab_changed = normalize_toc_tab_widths_xml(xml)
                changed += tab_changed
                xml, appendix_changed = prune_unexported_appendix_toc_xml(
                    xml, page_numbers
                )
                changed += appendix_changed
                raw = xml.encode("utf-8")
            target.writestr(info, raw)
    from .toc_columns import fixed_toc_columns

    data, column_changes = fixed_toc_columns(output.getvalue())
    return repack_hwpx_preserving_original_entries(data), changed + column_changes


def validate_toc_page_numbers(data: bytes, page_numbers: dict[str, str]) -> dict[str, object]:
    """Verify the final visible number beside every fixed TOC label."""

    with zipfile.ZipFile(BytesIO(data), "r") as source:
        xml = source.read("Contents/section1.xml").decode("utf-8")
    mismatches: list[str] = []
    actual: dict[str, str] = {}
    for key, label in TOC_SECTION2_LABELS.items():
        expected = str(page_numbers.get(key) or "").strip()
        if not expected:
            continue
        target = _toc_labeled_numeric_target(xml, label)
        raw_value = target[3].group(2) if target is not None else ""
        value = raw_value.strip()
        actual[key] = value
        if value != expected:
            mismatches.append(f"{label}: {value or '누락'} != {expected}")
        elif raw_value != expected:
            mismatches.append(f"{label}: 페이지 번호 앞뒤 공백 존재")
    if not any(
        str(page_numbers.get(key) or "").strip()
        for key in page_numbers
        if key.startswith("appendix_")
    ) and _normalized_toc_label(get_hwpx_xml_scope_text(xml)).find("첨부") >= 0:
        mismatches.append("미생성 첨부 목차가 남아 있음")
    return {"ok": not mismatches, "mismatches": mismatches, "actual": actual}
