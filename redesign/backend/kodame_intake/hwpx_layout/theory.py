from __future__ import annotations

import html
import re
import struct

from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans, get_hwpx_xml_scope_text


# Legacy fallback dimensions. PNG-backed exports derive source geometry from
# actual pixels (96 dpi), with a separate scale into the landscape frame.
THEORY_IMAGE_SOURCE_WIDTH = 160000
THEORY_IMAGE_SOURCE_HEIGHT = 90000
# section8 is rendered as A4 landscape.  Its 84,188-unit long edge and
# 5,669-unit left/right margins leave 72,850 units of usable width.  The old
# 46,000-unit frame was inherited from portrait pages, left the diagram stuck
# to the left edge, and made the six-column labels unnecessarily small.
# 70,400 keeps a 1,225-unit safety margin on either side and preserves the
# source's exact 16:9 aspect ratio.
THEORY_LANDSCAPE_BODY_WIDTH = 72850
THEORY_IMAGE_FRAME_WIDTH = 70400
THEORY_IMAGE_FRAME_HEIGHT = 39600
THEORY_IMAGE_SCALE = 0.44
THEORY_IMAGE_CENTER_X = THEORY_IMAGE_FRAME_WIDTH // 2
THEORY_IMAGE_CENTER_Y = THEORY_IMAGE_FRAME_HEIGHT // 2
THEORY_IMAGE_PARAGRAPH_PARA_PR_ID = 4


def _replace_picture_empty_tag(picture_xml: str, tag: str, replacement: str) -> str:
    return re.sub(rf"<{re.escape(tag)}\b[^>]*/>", replacement, picture_xml, count=1)


def force_lessons_page_break_xml(xml: str) -> tuple[str, bool]:
    """Keep the final lessons heading and landscape table on a new page."""

    heading_pos = xml.find("(2) 교훈")
    if heading_pos < 0:
        return xml, False
    paragraph_start = xml.rfind("<hp:p", 0, heading_pos)
    opening_end = xml.find(">", paragraph_start)
    if paragraph_start < 0 or opening_end < 0:
        return xml, False
    opening = xml[paragraph_start:opening_end + 1]
    adapted, count = re.subn(r'pageBreak="[01]"', 'pageBreak="1"', opening, count=1)
    if count != 1:
        return xml, False
    paragraph_end = xml.find("</hp:p>", opening_end)
    if paragraph_end < 0:
        return xml, False
    paragraph = adapted + xml[opening_end + 1:paragraph_end + len("</hp:p>")]
    if not re.search(r"<hp:t\b[^>]*>\s*<hp:lineBreak/>", paragraph):
        paragraph = re.sub(
            r"(<hp:t\b[^>]*>)",
            r"\1<hp:lineBreak/><hp:lineBreak/>",
            paragraph,
            count=1,
        )
    return xml[:paragraph_start] + paragraph + xml[paragraph_end + len("</hp:p>"):], True


def theory_image_source_size(png: bytes | None) -> tuple[int, int]:
    if png is None:
        return THEORY_IMAGE_SOURCE_WIDTH, THEORY_IMAGE_SOURCE_HEIGHT
    if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) < 24:
        raise ValueError('변화이론 이미지가 유효한 PNG가 아닙니다.')
    width, height = struct.unpack('>II', png[16:24])
    if not width or not height:
        raise ValueError('변화이론 이미지 크기가 비었습니다.')
    # HWP picture clipping uses 1/7200-inch units, 75 per 96-dpi pixel.
    return width * 75, height * 75


def replace_stale_theory_pictures_xml(xml: str, png: bytes | None = None) -> tuple[str, int, int]:
    """Keep only the current-project theory visual and remove two stale frames.

    ``image1`` is the Claude theory-of-change diagram. The template's next two
    sample frames formerly held DAC-grade and performance summaries, but those
    duplicate report content and are no longer reader-facing output.
    """

    source_width, source_height = theory_image_source_size(png)
    scale_x = THEORY_IMAGE_FRAME_WIDTH / source_width
    scale_y = THEORY_IMAGE_FRAME_HEIGHT / source_height
    spans = find_hwpx_tag_spans(xml, "hp:p")
    start_index = -1
    stop_index = len(spans)
    for index, (start, end) in enumerate(spans):
        paragraph = xml[start:end]
        visible = html.unescape(get_hwpx_xml_scope_text(paragraph)).strip()
        if start_index < 0 and "변화이론 분석" in visible:
            start_index = index
            continue
        if start_index >= 0 and "환류과제 및 교훈" in visible:
            stop_index = index
            break
    if start_index < 0:
        return xml, 0, 0
    targets = [
        spans[index]
        for index in range(start_index + 1, stop_index)
        if "<hp:pic" in xml[spans[index][0]:spans[index][1]]
    ]
    for start, end in reversed(targets[1:]):
        xml = xml[:start] + xml[end:]
    if targets:
        start, end = targets[0]
        picture_xml = xml[start:end]
        picture_xml, break_count = re.subn(
            r'(<hp:p\b[^>]*\bpageBreak=")[01](")',
            r'\g<1>1\2',
            picture_xml,
            count=1,
        )
        if break_count == 0:
            picture_xml = re.sub(r"<hp:p\b", '<hp:p pageBreak="1"', picture_xml, count=1)
        # Inline pictures follow the paragraph's alignment in Hancom/rHWP.
        # Use the template's zero-indent centered paragraph instead of the
        # former chapter-heading paragraph, which visually pinned the frame
        # to the left even though hp:pos requested CENTER.
        picture_xml, paragraph_style_count = re.subn(
            r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+',
            rf'\g<1>{THEORY_IMAGE_PARAGRAPH_PARA_PR_ID}',
            picture_xml,
            count=1,
        )
        if paragraph_style_count == 0:
            picture_xml = re.sub(
                r"<hp:p\b",
                f'<hp:p paraPrIDRef="{THEORY_IMAGE_PARAGRAPH_PARA_PR_ID}"',
                picture_xml,
                count=1,
            )
        picture_xml = re.sub(
            r'<hc:img\b[^>]*\bbinaryItemIDRef="[^"]+"',
            '<hc:img binaryItemIDRef="image1"',
            picture_xml,
            count=1,
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:offset",
            '<hp:offset x="0" y="0"/>',
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:orgSz",
            f'<hp:orgSz width="{source_width}" '
            f'height="{source_height}"/>',
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:curSz",
            f'<hp:curSz width="{THEORY_IMAGE_FRAME_WIDTH}" '
            f'height="{THEORY_IMAGE_FRAME_HEIGHT}"/>',
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:rotationInfo",
            f'<hp:rotationInfo angle="0" centerX="{THEORY_IMAGE_CENTER_X}" '
            f'centerY="{THEORY_IMAGE_CENTER_Y}" rotateimage="1"/>',
        )
        picture_xml = re.sub(
            r"<hp:renderingInfo>[\s\S]*?</hp:renderingInfo>",
            '<hp:renderingInfo>'
            '<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            f'<hc:scaMatrix e1="{scale_x}" e2="0" e3="0" e4="0" '
            f'e5="{scale_y}" e6="0"/>'
            '<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            '</hp:renderingInfo>',
            picture_xml,
            count=1,
        )
        picture_xml = re.sub(
            r"<hp:imgRect>[\s\S]*?</hp:imgRect>",
            '<hp:imgRect>'
            '<hc:pt0 x="0" y="0"/>'
            f'<hc:pt1 x="{source_width}" y="0"/>'
            f'<hc:pt2 x="{source_width}" y="{source_height}"/>'
            f'<hc:pt3 x="0" y="{source_height}"/>'
            '</hp:imgRect>',
            picture_xml,
            count=1,
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:imgClip",
            f'<hp:imgClip left="0" right="{source_width}" '
            f'top="0" bottom="{source_height}"/>',
        )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:imgDim",
            f'<hp:imgDim dimwidth="{source_width}" '
            f'dimheight="{source_height}"/>',
        )
        picture_xml, size_count = re.subn(
            r'<hp:sz\b[^>]*/>',
            f'<hp:sz width="{THEORY_IMAGE_FRAME_WIDTH}" widthRelTo="ABSOLUTE" '
            f'height="{THEORY_IMAGE_FRAME_HEIGHT}" '
            'heightRelTo="ABSOLUTE" protect="0"/>',
            picture_xml,
            count=1,
        )
        if size_count == 0:
            picture_xml = picture_xml.replace(
                "<hp:imgClip",
                f'<hp:sz width="{THEORY_IMAGE_FRAME_WIDTH}" widthRelTo="ABSOLUTE" '
                f'height="{THEORY_IMAGE_FRAME_HEIGHT}" '
                'heightRelTo="ABSOLUTE" protect="0"/><hp:imgClip',
                1,
            )
        picture_xml = _replace_picture_empty_tag(
            picture_xml,
            "hp:pos",
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
            'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
            'horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER" '
            'vertOffset="0" horzOffset="0"/>',
        )
        picture_xml = re.sub(
            r"<hp:shapeComment>[\s\S]*?</hp:shapeComment>",
            "<hp:shapeComment>현재 사업 근거로 생성한 변화이론 도식</hp:shapeComment>",
            picture_xml,
            count=1,
        )
        xml = xml[:start] + picture_xml + xml[end:]
    return xml, min(1, len(targets)), max(0, len(targets) - 1)


def attach_feedback_headings_to_table_xml(xml: str) -> tuple[str, bool]:
    """Move visible feedback headings immediately before their fixed table.

    A text run placed in the same paragraph as ``hp:tbl`` is ignored by the
    rHWP renderer.  Keep the chapter/subsection headings as independent
    paragraphs, force the chapter to a fresh page, and let the table follow it
    without another page break.  This prevents both the former blank page and
    the invisible-heading regression.
    """

    heading_spans: dict[str, tuple[int, int, str]] = {}
    table_span: tuple[int, int, str] | None = None
    for start, end in find_hwpx_tag_spans(xml, "hp:p"):
        paragraph = xml[start:end]
        visible = html.unescape(get_hwpx_xml_scope_text(paragraph)).strip()
        if "<hp:tbl" not in paragraph and visible in {"3. 환류과제 및 교훈", "(1) 환류과제"}:
            heading_spans[visible] = (start, end, paragraph)
        elif (
            "<hp:tbl" in paragraph
            and "평가 시 관찰사항" in visible
            and "환류과제" in visible
            and "이행부서" in visible
        ):
            table_span = (start, end, paragraph)
    if table_span is None or len(heading_spans) != 2:
        return xml, False

    table_start, table_end, table_paragraph = table_span

    def with_page_break(paragraph: str, enabled: bool) -> str:
        replacement = f'pageBreak="{1 if enabled else 0}"'
        updated, count = re.subn(r'pageBreak="[01]"', replacement, paragraph, count=1)
        if count:
            return updated
        return paragraph.replace("<hp:p ", f"<hp:p {replacement} ", 1)

    chapter_paragraph = with_page_break(
        heading_spans["3. 환류과제 및 교훈"][2], True,
    )
    subsection_paragraph = with_page_break(
        heading_spans["(1) 환류과제"][2], False,
    )
    table_paragraph = with_page_break(table_paragraph, False)
    updated_table_block = chapter_paragraph + subsection_paragraph + table_paragraph
    replacements = [
        (table_start, table_end, updated_table_block),
        (heading_spans["3. 환류과제 및 교훈"][0], heading_spans["3. 환류과제 및 교훈"][1], ""),
        (heading_spans["(1) 환류과제"][0], heading_spans["(1) 환류과제"][1], ""),
    ]
    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        xml = xml[:start] + replacement + xml[end:]
    return xml, True
