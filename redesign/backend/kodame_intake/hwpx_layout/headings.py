from __future__ import annotations

import binascii
import re
import zipfile
from dataclasses import dataclass
from html import escape
from io import BytesIO

from backend.oda_me.hwpx.patchers import (
    apply_hwpx_report_outline_style_xml,
    find_hwpx_tag_spans,
    get_hwpx_xml_scope_text,
    remove_hwpx_section_properties_xml,
    repack_hwpx_preserving_original_entries,
)


KEEP_WITH_NEXT_PARA_IDS = ("15", "31", "67", "69")
WIDOW_ORPHAN_PARA_IDS = ("71", "92")
MAJOR_CHAPTER_RE = re.compile(r"^(?:[IVX]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)[.]\s*\S", re.IGNORECASE)
EVALUATION_CRITERION_RE = re.compile(
    r"^[1-7][.]\s*(?:적절성|일관성|효과성|효율성|지속가능성|범분야\s*이슈|그\s*외\s*평가기준)\s*$"
)
FORCED_CRITERION_PAGE_BREAK_LABELS = {
    "2. 일관성",
    "3. 효과성",
    "5. 지속가능성",
    "6. 범분야 이슈",
    "7. 그 외 평가기준",
}


@dataclass(frozen=True)
class HeadingLayoutStats:
    major_chapters: int = 0
    section_headings: int = 0


def style_project_background_subheadings_xml(xml: str) -> tuple[str, int]:
    """Render each background slot as one hanging ``ㅇ`` paragraph.

    The title remains bold on the first line. The evidence paragraph begins
    after an explicit line break inside the same bullet paragraph, so rHWP
    aligns every continuation line with the prose position after ``ㅇ``.
    """

    paragraphs = find_hwpx_tag_spans(xml, "hp:p")
    texts = [re.sub(r"\s+", " ", get_hwpx_xml_scope_text(xml[start:end])).strip() for start, end in paragraphs]
    start_index = next((i for i, text in enumerate(texts) if text == "1. 사업 추진배경"), -1)
    end_index = next((i for i, text in enumerate(texts) if i > start_index and text == "2. 사업개요"), len(paragraphs))
    if start_index < 0:
        return xml, 0

    changed = 0
    for index in range(end_index - 1, start_index, -1):
        start, end = paragraphs[index]
        paragraph = xml[start:end]
        if "<hp:tbl" in paragraph:
            continue
        text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip()
        match = re.match(r"^\(([^()]{2,90})\)\s+(.{10,})$", text)
        if not match:
            continue
        title, body = match.groups()
        rendered = remove_hwpx_section_properties_xml(paragraph)
        rendered = apply_hwpx_report_outline_style_xml(rendered, "bullet")
        opening = re.match(r"<hp:p\b[^>]*>", rendered)
        closing_at = rendered.rfind("</hp:p>")
        if not opening or closing_at < 0:
            continue
        paragraph_id = binascii.crc32(
            f"background|{title}|{body[:80]}".encode("utf-8")
        ) & 0xFFFFFFFF
        opening_xml = re.sub(
            r'(<hp:p\b[^>]*\bid=")\d+',
            rf"\g<1>{paragraph_id}",
            opening.group(0),
            count=1,
        )
        rendered = (
            opening_xml
            + '<hp:run charPrIDRef="18"><hp:t>'
            + escape(f"ㅇ ({title.strip()})")
            + "</hp:t></hp:run>"
            + '<hp:run charPrIDRef="28"><hp:t><hp:lineBreak/>'
            + escape(body.strip())
            + "</hp:t></hp:run></hp:p>"
        )
        xml = xml[:start] + rendered + xml[end:]
        changed += 1
    return xml, changed


def _patch_break_setting(xml: str, para_pr_id: str, attribute: str, value: int) -> str:
    pattern = re.compile(
        rf'(<hh:paraPr\b[^>]*\bid="{para_pr_id}"[^>]*>)(.*?)(</hh:paraPr>)',
        re.DOTALL,
    )
    match = pattern.search(xml)
    if not match:
        return xml
    paragraph = match.group(0)
    paragraph = re.sub(
        rf'(<hh:breakSetting\b[^>]*\b{attribute}=")[01](")',
        rf"\g<1>{value}\2",
        paragraph,
        count=1,
    )
    return xml[:match.start()] + paragraph + xml[match.end():]


def patch_heading_pagination_header_xml(xml: str) -> str:
    """Enable heading cohesion and body widow/orphan protection by role."""

    for para_pr_id in KEEP_WITH_NEXT_PARA_IDS:
        xml = _patch_break_setting(xml, para_pr_id, "keepWithNext", 1)
    for para_pr_id in WIDOW_ORPHAN_PARA_IDS:
        xml = _patch_break_setting(xml, para_pr_id, "widowOrphan", 1)
    return xml


def _opening_para_pr(paragraph: str) -> str:
    opening = re.match(r"<hp:p\b[^>]*>", paragraph)
    if not opening:
        return ""
    match = re.search(r'\bparaPrIDRef="(\d+)"', opening.group(0))
    return match.group(1) if match else ""


def _replace_opening_style(paragraph: str, para_pr_id: int) -> str:
    return re.sub(
        r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*\bstyleIDRef=")\d+("[^>]*>)',
        rf"\g<1>{para_pr_id}\g<2>0\3",
        paragraph,
        count=1,
    )


def _set_explicit_page_break(paragraph: str) -> str:
    """Set the break before a paragraph that RHWP honors over defaults."""

    opening = re.match(r"<hp:p\b[^>]*>", paragraph)
    if not opening:
        return paragraph
    tag = opening.group(0)
    if re.search(r'\bpageBreak="[01]"', tag):
        updated = re.sub(r'(\bpageBreak=")[01](")', r'\g<1>1\2', tag, count=1)
    else:
        updated = tag[:-1] + ' pageBreak="1">'
    return updated + paragraph[opening.end() :]


def _replace_direct_run_char_style(paragraph: str, char_pr_id: int) -> str:
    """Change heading runs without touching runs inside an embedded table."""

    table_at = paragraph.find("<hp:tbl")
    prefix = paragraph if table_at < 0 else paragraph[:table_at]
    suffix = "" if table_at < 0 else paragraph[table_at:]
    prefix = re.sub(
        r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+("[^>]*>)',
        rf"\g<1>{char_pr_id}\2",
        prefix,
    )
    return prefix + suffix


def normalize_heading_hierarchy_xml(xml: str) -> tuple[str, HeadingLayoutStats]:
    """Apply one visual hierarchy to chapter and first-level section titles."""

    table_spans = find_hwpx_tag_spans(xml, "hp:tbl")
    major_count = 0
    section_count = 0
    for start, end in reversed(find_hwpx_tag_spans(xml, "hp:p")):
        if any(table_start < start and end < table_end for table_start, table_end in table_spans):
            continue
        paragraph = xml[start:end]
        prefix = paragraph.split("<hp:tbl", 1)[0]
        text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(prefix)).strip()
        if not text:
            continue
        if MAJOR_CHAPTER_RE.match(text):
            updated = _replace_opening_style(paragraph, 31)
            updated = _replace_direct_run_char_style(updated, 63)
            major_count += int(updated != paragraph)
        elif _opening_para_pr(paragraph) == "15":
            updated = _replace_direct_run_char_style(paragraph, 76)
            section_count += int(updated != paragraph)
        else:
            continue
        if updated != paragraph:
            xml = xml[:start] + updated + xml[end:]
    return xml, HeadingLayoutStats(major_count, section_count)


def _patch_heading_page_breaks_xml(xml: str, headings: set[str]) -> tuple[str, int]:
    table_spans = find_hwpx_tag_spans(xml, "hp:tbl")
    changed = 0
    for start, end in reversed(find_hwpx_tag_spans(xml, "hp:p")):
        if any(table_start < start and end < table_end for table_start, table_end in table_spans):
            continue
        paragraph = xml[start:end]
        text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip()
        if text not in headings:
            continue
        updated = _set_explicit_page_break(paragraph)
        if updated != paragraph:
            xml = xml[:start] + updated + xml[end:]
            changed += 1
    return xml, changed


def heading_starts_on_fresh_page_xml(xml: str, heading: str) -> bool:
    """Return whether the heading carries RHWP's explicit pre-page break."""

    table_spans = find_hwpx_tag_spans(xml, "hp:tbl")
    paragraphs: list[str] = []
    texts: list[str] = []
    for start, end in find_hwpx_tag_spans(xml, "hp:p"):
        if any(table_start < start and end < table_end for table_start, table_end in table_spans):
            continue
        paragraph = xml[start:end]
        text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip()
        if text:
            paragraphs.append(paragraph)
            texts.append(text)
    try:
        index = texts.index(heading)
    except ValueError:
        return False
    heading_opening = re.match(r"<hp:p\b[^>]*>", paragraphs[index])
    return bool(heading_opening and 'pageBreak="1"' in heading_opening.group(0))


def force_numbered_criterion_page_breaks_xml(xml: str) -> tuple[str, int]:
    """Start criteria 2–7 on a fresh page instead of after prior prose.

    ``1. 적절성`` remains attached to the immediately preceding chapter and
    ``4. 효율성`` begins a new physical HWPX section already.  For the other
    peer criteria, the heading itself receives RHWP's explicit pre-page break
    so the new page starts with the numbered title.
    """

    return _patch_heading_page_breaks_xml(xml, FORCED_CRITERION_PAGE_BREAK_LABELS)


def patch_orphan_heading_page_breaks(data: bytes, headings: set[str]) -> tuple[bytes, int]:
    """Move only renderer-confirmed orphan headings to the following RHWP page."""

    if not headings:
        return data, 0
    output = BytesIO()
    changed = 0
    with zipfile.ZipFile(BytesIO(data), "r") as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename in ("Contents/section6.xml", "Contents/section7.xml"):
                xml, section_changed = _patch_heading_page_breaks_xml(raw.decode("utf-8"), headings)
                changed += section_changed
                raw = xml.encode("utf-8")
            target.writestr(info, raw)
    return repack_hwpx_preserving_original_entries(output.getvalue()), changed
