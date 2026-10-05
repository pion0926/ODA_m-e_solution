from __future__ import annotations

import re
import zipfile
from io import BytesIO

from backend.oda_me.hwpx.patchers import (
    find_hwpx_all_tag_spans,
    find_hwpx_tag_spans,
    get_hwpx_xml_scope_text,
)
from backend.oda_me.reports.citations import strip_inline_source_citations

from .headings import (
    FORCED_CRITERION_PAGE_BREAK_LABELS,
    heading_starts_on_fresh_page_xml,
    KEEP_WITH_NEXT_PARA_IDS,
    WIDOW_ORPHAN_PARA_IDS,
)
from .page_identity import APPLY_FROM_SECTION, PAGE_NUMBER_POSITION
from .project_overview import CANONICAL_HEADING, TABLE_CELL_MARGIN_VERTICAL, TABLE_PAGE_BUDGET
from .recommendations import (
    FEEDBACK_ROWS_PER_PAGE,
    LESSONS_MAX_TABLE_HEIGHT,
    LESSONS_ROWS_PER_PAGE,
)
from .spacing import (
    EVALUATION_OVERVIEW_CHAPTER_HEADING,
    heading_has_blank_line_before_xml,
    heading_starts_on_fresh_page_xml as spacing_heading_starts_on_fresh_page_xml,
    report_heading_gap_violations_xml,
)
from .grade_table import (
    GRADE_CELL_MARGIN_HORIZONTAL,
    GRADE_CELL_MARGIN_VERTICAL,
    GRADE_HEADER_ROW_HEIGHT,
    GRADE_QUESTION_MIN_HEIGHT,
    GRADE_QUESTION_MAX_HEIGHT,
    GRADE_SUBTOTAL_ROW_HEIGHT,
    GRADE_SUMMARY_ROW_HEIGHT,
    GRADE_TABLE_PAGE_ROW_GROUPS,
    grade_question_row_height,
)
from .toc import (
    ACHIEVEMENT_TOC_PARA_PR_ID,
    TOC_RIGHT_TAB_POSITION,
    TOC_RIGHT_TAB_PR_ID,
)
from .theory import (
    theory_image_source_size,
    THEORY_IMAGE_CENTER_X,
    THEORY_IMAGE_CENTER_Y,
    THEORY_IMAGE_FRAME_HEIGHT,
    THEORY_IMAGE_FRAME_WIDTH,
    THEORY_IMAGE_PARAGRAPH_PARA_PR_ID,
    THEORY_IMAGE_SCALE,
    THEORY_IMAGE_SOURCE_HEIGHT,
    THEORY_IMAGE_SOURCE_WIDTH,
    THEORY_LANDSCAPE_BODY_WIDTH,
)
from .tables import (
    achievement_page_groups,
    ACHIEVEMENT_GROUP_MIN_HEIGHT,
    ACHIEVEMENT_HEADER_ROW_COUNT,
    ACHIEVEMENT_HEADER_ROW_HEIGHTS,
    ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
    ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS,
    ACHIEVEMENT_PAGE_HEIGHT,
    ACHIEVEMENT_FIRST_PAGE_HEIGHT,
    EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL,
    EVALUATION_MATRIX_CELL_MARGIN_VERTICAL,
    EVALUATION_MATRIX_HEADER_ROW_HEIGHT,
    EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS,
    PDM_TABLE_PAGE_ROW_GROUPS,
    PDM_MAXIMUM_TABLE_HEIGHT,
    achievement_item_group_height,
    achievement_item_group_physical_heights,
    evaluation_matrix_row_height,
)


def _header_property_enabled(header: str, para_pr_id: str, attribute: str) -> bool:
    match = re.search(
        rf'<hh:paraPr\b[^>]*\bid="{para_pr_id}"[^>]*>.*?<hh:breakSetting\b([^>]*)/>.*?</hh:paraPr>',
        header,
        re.DOTALL,
    )
    return bool(match and re.search(rf'\b{attribute}="1"', match.group(1)))


def _has_inline_source_citation(value: object) -> bool:
    """Ignore semantic run-boundary whitespace while detecting citations."""

    text = str(value or "")

    def comparable(item: str) -> str:
        item = re.sub(r"[ \t]{2,}", " ", item)
        item = re.sub(r"\s+([,.;:!?。、])", r"\1", item)
        item = re.sub(r"([.!?。])\1+", r"\1", item)
        return item.strip()

    return comparable(strip_inline_source_citations(text)) != comparable(text)


def _paragraph_for_text(xml: str, needle: str) -> str:
    return next(
        (
            xml[start:end]
            for start, end in find_hwpx_tag_spans(xml, "hp:p")
            if needle in get_hwpx_xml_scope_text(xml[start:end]) and "<hp:tbl" not in xml[start:end]
        ),
        "",
    )


def validate_report_layout_contract(data: bytes) -> dict:
    """Fail-fast audit for the typography and pagination rules we own."""

    errors: list[str] = []
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        theory_source_width, theory_source_height = theory_image_source_size(archive.read("BinData/image1.png"))
        header = archive.read("Contents/header.xml").decode("utf-8")
        sections = {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if re.fullmatch(r"Contents/section\d+\.xml", name)
        }

    for para_pr_id in KEEP_WITH_NEXT_PARA_IDS:
        if not _header_property_enabled(header, para_pr_id, "keepWithNext"):
            errors.append(f"제목 문단 {para_pr_id} keepWithNext 미적용")
    for para_pr_id in WIDOW_ORPHAN_PARA_IDS:
        if not _header_property_enabled(header, para_pr_id, "widowOrphan"):
            errors.append(f"본문 문단 {para_pr_id} widowOrphan 미적용")
    remaining_colors = [
        color
        for color in re.findall(r'<hh:charPr\b[^>]*\btextColor="([^"]+)"', header)
        if color.lower() not in {"#000000", "#ffffff"}
    ]
    if remaining_colors:
        errors.append(f"전역 본문 글자색 검정 정규화 누락: {sorted(set(remaining_colors))}")
    for section_name, section_xml in sections.items():
        visible_text = get_hwpx_xml_scope_text(section_xml)
        if _has_inline_source_citation(visible_text):
            errors.append(f"본문 문서명·페이지 위치 인용 잔존: {section_name}")
        match = re.search(r"section(\d+)\.xml$", section_name)
        section_index = int(match.group(1)) if match else -1
        if section_index >= APPLY_FROM_SECTION and (
            f'<hp:pageNum pos="{PAGE_NUMBER_POSITION}"' not in section_xml
        ):
            errors.append(f"본문 쪽번호 활성화 누락: {section_name}")
    achievement_para_pr = re.search(
        rf'<hh:paraPr\b(?=[^>]*\bid="{ACHIEVEMENT_TOC_PARA_PR_ID}")[^>]*>',
        header,
    )
    if not achievement_para_pr or f'tabPrIDRef="{TOC_RIGHT_TAB_PR_ID}"' not in achievement_para_pr.group(0):
        errors.append("목차 성과달성도 문단 우측 탭 스타일 미적용")
    right_tab_pr = re.search(
        rf'<hh:tabPr\b[^>]*\bid="{TOC_RIGHT_TAB_PR_ID}"[^>]*>.*?</hh:tabPr>',
        header,
        re.DOTALL,
    )
    if not right_tab_pr or not all(
        token in right_tab_pr.group(0)
        for token in (f'pos="{TOC_RIGHT_TAB_POSITION}"', 'type="RIGHT"', 'leader="DASH"')
    ):
        errors.append("목차 우측 점선 탭 정의 불일치")
    cover = sections.get("Contents/section0.xml", "")
    for start, end in find_hwpx_tag_spans(cover, "hp:p"):
        paragraph = cover[start:end]
        if 'charPrIDRef="58"' not in paragraph:
            continue
        lines = [
            re.sub(r"\s+", " ", get_hwpx_xml_scope_text(part)).strip()
            for part in paragraph.split("<hp:lineBreak/>")
        ]
        if any(line in {"및", "과", "와", "and", "or", "·"} for line in lines):
            errors.append("표지 제목 접속사 단독 줄")

    conclusion = _paragraph_for_text(sections.get("Contents/section7.xml", ""), "VI. 결론")
    if not conclusion:
        errors.append("VI. 결론 문단 누락")
    else:
        opening = re.match(r"<hp:p\b[^>]*>", conclusion)
        if not opening or 'paraPrIDRef="31"' not in opening.group(0):
            errors.append("VI. 결론 장 제목 문단 스타일 불일치")
        prefix = conclusion.split("<hp:tbl", 1)[0]
        if 'charPrIDRef="63"' not in prefix:
            errors.append("VI. 결론 16pt Bold 스타일 불일치")

    pdm = sections.get("Contents/section4.xml", "")
    pdm_tables = [
        pdm[start:end]
        for start, end in find_hwpx_tag_spans(pdm, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(pdm[start:end])
            for token in ("프로그램 요약", "객관적 검증지표", "중요가정")
        )
    ]
    if len(pdm_tables) != len(PDM_TABLE_PAGE_ROW_GROUPS):
        errors.append(
            f"PDM 결과수준별 분할 불일치: {len(pdm_tables)}/{len(PDM_TABLE_PAGE_ROW_GROUPS)}"
        )
    for table_index, (pdm_table, row_group) in enumerate(
        zip(pdm_tables, PDM_TABLE_PAGE_ROW_GROUPS),
        start=1,
    ):
        if any(f'charPrIDRef="{char_id}"' in pdm_table for char_id in ("74", "79", "81", "82", "84")):
            errors.append(f"PDM {table_index}쪽 8pt 미만 글자 스타일 잔존")
        rows = find_hwpx_tag_spans(pdm_table, "hp:tr")
        if len(rows) != len(row_group):
            errors.append(
                f"PDM {table_index}쪽 행 구성 불일치: {len(rows)}/{len(row_group)}"
            )
        if not all(
            attribute in pdm_table
            for attribute in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
        ):
            errors.append(f"PDM {table_index}쪽 페이지 안전 정책 불일치")
        if any(
            phrase in get_hwpx_xml_scope_text(pdm_table)
            for phrase in (
                "Narrative Summary",
                "Objectively Verifiable Indicators",
                "Means of Verification",
                "Important Assumption",
            )
        ):
            errors.append(f"PDM {table_index}쪽 장문 영문 머리행 잔존")
        table_size = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', pdm_table)
        if not table_size or int(table_size.group(1)) > PDM_MAXIMUM_TABLE_HEIGHT:
            errors.append(
                f"PDM 1쪽 최대 높이 초과: "
                f"{table_size.group(1) if table_size else '없음'}/{PDM_MAXIMUM_TABLE_HEIGHT}"
            )

    matrix_heading = _paragraph_for_text(pdm, "2. 평가매트릭스(Evaluation Matrix)")
    matrix_heading_opening = re.match(r"<hp:p\b[^>]*>", matrix_heading) if matrix_heading else None
    if not matrix_heading_opening or not all(
        token in matrix_heading_opening.group(0)
        for token in ('paraPrIDRef="31"', 'pageBreak="1"')
    ):
        errors.append("평가매트릭스 제목 새 쪽·상단 여백 스타일 불일치")

    matrix_tables = [
        pdm[start:end]
        for start, end in find_hwpx_tag_spans(pdm, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(pdm[start:end])
            for token in ("평가기준", "평가질문", "분석방법")
        )
    ]
    if not matrix_tables:
        errors.append("평가매트릭스 표 누락")
    if "평가매트릭스 상세 M" in get_hwpx_xml_scope_text(pdm):
        errors.append("평가매트릭스 별도 상세 본문 잔존")
    if any("…" in get_hwpx_xml_scope_text(table) for table in matrix_tables):
        errors.append("평가매트릭스 셀 생략부호 잔존")
    expected_matrix_margin = (
        f'left="{EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL}"',
        f'right="{EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL}"',
        f'top="{EVALUATION_MATRIX_CELL_MARGIN_VERTICAL}"',
        f'bottom="{EVALUATION_MATRIX_CELL_MARGIN_VERTICAL}"',
    )
    for table_index, matrix_table in enumerate(matrix_tables, start=1):
        if not all(
            attribute in matrix_table
            for attribute in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
        ):
            errors.append(f"평가매트릭스 {table_index}쪽 분할 정책 불일치")
        margin = re.search(r"<hp:inMargin\b[^>]*/>", matrix_table)
        if not margin or not all(token in margin.group(0) for token in expected_matrix_margin):
            errors.append(f"평가매트릭스 {table_index}쪽 기본 셀 여백 불일치")
        if any(
            not all(token in cell_margin for token in expected_matrix_margin)
            for cell_margin in re.findall(r"<hp:cellMargin\b[^>]*/>", matrix_table)
        ):
            errors.append(f"평가매트릭스 {table_index}쪽 개별 셀 여백 불일치")
        rows = find_hwpx_tag_spans(matrix_table, "hp:tr")
        if len(rows) < 2:
            errors.append(f"평가매트릭스 {table_index}쪽 본문 행 누락")
            continue
        table_height = 0
        for row_index, (row_start, row_end) in enumerate(rows):
            row = matrix_table[row_start:row_end]
            cells = [row[start:end] for start, end in find_hwpx_tag_spans(row, "hp:tc")]
            heights = [
                int(match.group(1))
                for cell in cells
                if (match := re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell))
            ]
            expected_height = evaluation_matrix_row_height(row, row_index)
            if not heights or any(height != expected_height for height in heights):
                errors.append(
                    f"평가매트릭스 {table_index}쪽 {row_index}행 높이 불일치"
                    f"(실제 {heights or '없음'}, 기대 {expected_height})"
                )
            if row_index == 0 and expected_height != EVALUATION_MATRIX_HEADER_ROW_HEIGHT:
                errors.append(f"평가매트릭스 {table_index}쪽 머리행 높이 불일치")
            if any(f'rowAddr="{row_index}"' not in cell for cell in cells):
                errors.append(f"평가매트릭스 {table_index}쪽 {row_index}행 주소 불일치")
            table_height += expected_height
        if table_height > 60000:
            errors.append(f"평가매트릭스 {table_index}쪽 인쇄 영역 초과")
        table_size = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', matrix_table)
        if not table_size or int(table_size.group(1)) != table_height:
            errors.append(
                f"평가매트릭스 {table_index}쪽 전체 높이 불일치"
                f"(실제 {table_size.group(1) if table_size else '없음'}, 기대 {table_height})"
            )

    achievement = sections.get("Contents/section5.xml", "")
    if 'charPrIDRef="43"' in achievement or 'charPrIDRef="44"' in achievement:
        errors.append("성과달성도 표 8pt 글자 스타일 잔존")
    achievement_tables = [
        achievement[start:end]
        for start, end in find_hwpx_tag_spans(achievement, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(achievement[start:end])
            for token in ("성과지표", "기초선", "달성도")
        )
    ]
    achievement_item_count = sum(max(0, len(find_hwpx_tag_spans(table, "hp:tr")) - ACHIEVEMENT_HEADER_ROW_COUNT) for table in achievement_tables) // ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
    achievement_heights=[]
    for table in achievement_tables:
        rows=[table[a:b] for a,b in find_hwpx_tag_spans(table,'hp:tr')][ACHIEVEMENT_HEADER_ROW_COUNT:]
        achievement_heights.extend(achievement_item_group_height(''.join(rows[i:i+3])) for i in range(0,len(rows),3))
    current_achievement_groups = achievement_page_groups(achievement_item_count,achievement_heights)
    if not achievement_tables or len(achievement_tables) != len(current_achievement_groups):
        errors.append(
            f"성과달성도 표 페이지 분할 불일치: "
            f"{len(achievement_tables)}/{len(current_achievement_groups)}"
        )
    if any("…" in get_hwpx_xml_scope_text(table) for table in achievement_tables):
        errors.append("성과달성도 표 셀 생략부호 잔존")
    for table_index, (achievement_table, item_group) in enumerate(
        zip(achievement_tables, current_achievement_groups),
        start=1,
    ):
        if not all(
            attribute in achievement_table
            for attribute in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
        ):
            errors.append(f"성과달성도 표 {table_index}쪽 분할 정책 불일치")
        achievement_rows = find_hwpx_tag_spans(achievement_table, "hp:tr")
        expected_row_count = ACHIEVEMENT_HEADER_ROW_COUNT + (
            len(item_group) * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
        )
        if len(achievement_rows) != expected_row_count:
            errors.append(
                f"성과달성도 표 {table_index}쪽 행 구성 불일치: "
                f"{len(achievement_rows)}/{expected_row_count}"
            )
        expected_body_count = len(achievement_rows) - ACHIEVEMENT_HEADER_ROW_COUNT
        if expected_body_count <= 0 or expected_body_count % ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
            errors.append(f"성과달성도 표 {table_index}쪽 지표별 3행 구조 불일치")
        else:
            physical_row_heights: list[int] = []
            for row_index, (row_start, row_end) in enumerate(achievement_rows):
                row = achievement_table[row_start:row_end]
                regular_heights: list[int] = []
                all_heights: list[int] = []
                for cell_start, cell_end in find_hwpx_tag_spans(row, "hp:tc"):
                    cell = row[cell_start:cell_end]
                    height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
                    if not height:
                        continue
                    value = int(height.group(1))
                    all_heights.append(value)
                    row_span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
                    if not row_span or int(row_span.group(1)) == 1:
                        regular_heights.append(value)
                physical_row_heights.append(min(regular_heights or all_heights or [0]))
                cells = [
                    row[cell_start:cell_end]
                    for cell_start, cell_end in find_hwpx_tag_spans(row, "hp:tc")
                ]
                if any(f'rowAddr="{row_index}"' not in cell for cell in cells):
                    errors.append(f"성과달성도 표 {table_index}쪽 {row_index}행 주소 불일치")

                if row_index < ACHIEVEMENT_HEADER_ROW_COUNT:
                    continue
                if any(height <= 0 for height in all_heights):
                    errors.append(f"성과달성도 표 {table_index}쪽 {row_index}행 0 높이 셀 잔존")
                if any(
                    not re.search(r'<hp:subList\b[^>]*\bvertAlign="TOP"', cell)
                    for cell in cells
                ):
                    errors.append(
                        f"성과달성도 표 {table_index}쪽 {row_index}행 본문 셀 상단 정렬 누락"
                    )

            for group_start in range(
                ACHIEVEMENT_HEADER_ROW_COUNT,
                len(achievement_rows),
                ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
            ):
                group_rows = [
                    achievement_table[row_start:row_end]
                    for row_start, row_end in achievement_rows[
                        group_start : group_start + ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
                    ]
                ]
                expected_physical_heights = list(
                    achievement_item_group_physical_heights(group_rows)
                )
                expected_height = achievement_item_group_height("".join(group_rows))
                actual_height = sum(
                    physical_row_heights[group_start : group_start + ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM]
                )
                if expected_height < ACHIEVEMENT_GROUP_MIN_HEIGHT or actual_height != expected_height:
                    errors.append(
                        f"성과달성도 표 {group_start}행 지표 묶음 높이 불일치: "
                        f"{actual_height}/{expected_height}"
                    )
                actual_physical_heights = physical_row_heights[
                    group_start : group_start + ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
                ]
                if actual_physical_heights != expected_physical_heights:
                    errors.append(
                        f"성과달성도 표 {table_index}쪽 {group_start}행 내용기반 물리 높이 불일치: "
                        f"{actual_physical_heights}/{expected_physical_heights}"
                    )
                for row_offset, row in enumerate(group_rows):
                    for cell_start, cell_end in find_hwpx_tag_spans(row, "hp:tc"):
                        cell = row[cell_start:cell_end]
                        span_match = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
                        span_count = int(span_match.group(1)) if span_match else 1
                        if span_count <= 1:
                            continue
                        expected_span_height = sum(
                            expected_physical_heights[
                                row_offset : min(len(expected_physical_heights), row_offset + span_count)
                            ]
                        )
                        height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
                        if not height or int(height.group(1)) != expected_span_height:
                            errors.append(
                                f"성과달성도 표 {table_index}쪽 {group_start + row_offset}행 "
                                "병합 셀 높이 불일치"
                            )
                            break

            if physical_row_heights[:ACHIEVEMENT_HEADER_ROW_COUNT] != list(
                ACHIEVEMENT_HEADER_ROW_HEIGHTS
            ):
                errors.append(
                    f"성과달성도 표 {table_index}쪽 머리행 높이 불일치: "
                    f"{physical_row_heights[:ACHIEVEMENT_HEADER_ROW_COUNT]}"
                )

            table_size = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', achievement_table)
            expected_table_height = sum(physical_row_heights)
            if expected_table_height > (ACHIEVEMENT_FIRST_PAGE_HEIGHT if table_index==1 else ACHIEVEMENT_PAGE_HEIGHT):
                errors.append(f'성과달성도 표 {table_index}쪽 인쇄 높이 초과')
            if not table_size or int(table_size.group(1)) != expected_table_height:
                errors.append(
                    f"성과달성도 표 전체 높이 불일치: "
                    f"{table_size.group(1) if table_size else '누락'}/{expected_table_height}"
                )
    if achievement_tables and len(re.findall(r'<hp:p\b[^>]*\bpageBreak="1"', achievement)) < len(current_achievement_groups) - 1:
        errors.append("성과달성도 표 사이 강제 쪽 나눔 누락")

    grade = sections.get("Contents/section2.xml", "")
    grade_tables = [
        grade[start:end]
        for start, end in find_hwpx_tag_spans(grade, "hp:tbl")
        if "평가 기준" in get_hwpx_xml_scope_text(grade[start:end])
        and "핵심 질문" in get_hwpx_xml_scope_text(grade[start:end])
    ]
    if not grade_tables:
        errors.append("평가등급 결과표 누락")
    else:
        question_count = subtotal_count = summary_count = 0
        expected_margin_parts = (
            f'left="{GRADE_CELL_MARGIN_HORIZONTAL}"',
            f'right="{GRADE_CELL_MARGIN_HORIZONTAL}"',
            f'top="{GRADE_CELL_MARGIN_VERTICAL}"',
            f'bottom="{GRADE_CELL_MARGIN_VERTICAL}"',
        )
        for part_index, grade_table in enumerate(grade_tables, start=1):
            if not all(
                attribute in grade_table
                for attribute in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
            ):
                errors.append(f"평가등급 결과표 {part_index}쪽 분할 정책 불일치")
            grade_margin = re.search(r"<hp:inMargin\b[^>]*/>", grade_table)
            if not grade_margin or not all(part in grade_margin.group(0) for part in expected_margin_parts):
                errors.append(f"평가등급 결과표 {part_index}쪽 셀 여백 불일치")

            grade_rows = find_hwpx_tag_spans(grade_table, "hp:tr")
            table_height = 0
            for row_index, (row_start, row_end) in enumerate(grade_rows):
                row = grade_table[row_start:row_end]
                row_text = get_hwpx_xml_scope_text(row).strip()
                cells = [row[start:end] for start, end in find_hwpx_tag_spans(row, "hp:tc")]
                if any(f'rowAddr="{row_index}"' not in cell for cell in cells):
                    errors.append(f"평가등급 결과표 {part_index}쪽 {row_index}행 주소 불일치")
                regular_heights = []
                for cell in cells:
                    if 'rowSpan="1"' not in cell:
                        continue
                    height = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', cell)
                    if height:
                        regular_heights.append(int(height.group(1)))
                if not regular_heights:
                    errors.append(f"평가등급 결과표 {part_index}쪽 {row_index}행 높이 누락")
                    continue
                row_height = min(regular_heights)
                table_height += row_height

                if row_index == 0:
                    if row_height != GRADE_HEADER_ROW_HEIGHT:
                        errors.append(f"평가등급 결과표 {part_index}쪽 머리행 높이 불일치")
                    continue
                if "평점(" in row_text:
                    subtotal_count += 1
                    if row_height != GRADE_SUBTOTAL_ROW_HEIGHT:
                        errors.append(f"평가등급 결과표 {part_index}쪽 평점행 높이 불일치")
                    reason_cell = next((cell for cell in cells if 'colAddr="4"' in cell), "")
                    if reason_cell and get_hwpx_xml_scope_text(reason_cell).strip():
                        errors.append(f"평가등급 결과표 {part_index}쪽 평점행 산정 이유 잔존")
                    continue
                if any(label in row_text for label in ("종합 점수", "종합 평가 등급", "KOICA 평가등급")):
                    summary_count += 1
                    if row_height != GRADE_SUMMARY_ROW_HEIGHT:
                        errors.append(f"평가등급 결과표 {part_index}쪽 종합결과행 높이 불일치")
                    continue

                question_count += 1
                expected_question_height = grade_question_row_height(row)
                if row_height != expected_question_height:
                    errors.append(
                        f"평가등급 결과표 {part_index}쪽 질문행 내용기반 높이 불일치: "
                        f"{row_height}/{expected_question_height}"
                    )
                if not GRADE_QUESTION_MIN_HEIGHT <= row_height <= GRADE_QUESTION_MAX_HEIGHT:
                    errors.append(f"평가등급 결과표 {part_index}쪽 질문행 높이 범위 이탈")
                question_cell = next((cell for cell in cells if 'colAddr="1"' in cell), "")
                reason_cell = next((cell for cell in cells if 'colAddr="4"' in cell), "")
                if "<hp:lineBreak/>" not in question_cell or 'paraPrIDRef="39"' not in question_cell:
                    errors.append(f"평가등급 결과표 {part_index}쪽 핵심 질문 줄바꿈·정렬 불일치")
                if not get_hwpx_xml_scope_text(reason_cell).strip() or 'paraPrIDRef="39"' not in reason_cell:
                    errors.append(f"평가등급 결과표 {part_index}쪽 질문 산정 이유 누락·정렬 불일치")
                if "<hp:tab" in reason_cell or "\t" in get_hwpx_xml_scope_text(reason_cell):
                    errors.append(f"평가등급 결과표 {part_index}쪽 질문 산정 이유 TAB 잔존")

            table_size = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', grade_table)
            # Reserve space for the title and wrapped project name above the
            # first table. Text presence alone does not prove it is on-page.
            page_budget = 58000 if part_index == 1 else 65000
            if table_height > page_budget:
                errors.append(f"평가등급 결과표 {part_index}쪽 인쇄 영역 초과: {table_height}/{page_budget}")
            if not table_size or int(table_size.group(1)) != table_height:
                errors.append(f"평가등급 결과표 {part_index}쪽 전체 높이 불일치")
        if (question_count, subtotal_count, summary_count) != (11, 5, 3):
            errors.append(
                "평가등급 결과표 행 구성 불일치: "
                f"질문 {question_count}/11, 평점 {subtotal_count}/5, 종합 {summary_count}/3"
            )
        expected_breaks = len(grade_tables) - 1
        if len(re.findall(r'<hp:p\b[^>]*\bpageBreak="1"', grade)) < expected_breaks:
            errors.append(f"평가등급 결과표 쪽 나눔 문단 {expected_breaks}개 누락")

    background = sections.get("Contents/section3.xml", "")
    overview_heading = _paragraph_for_text(background, CANONICAL_HEADING)
    overview_opening = re.match(r"<hp:p\b[^>]*>", overview_heading) if overview_heading else None
    if not overview_heading or "사업개요서 최종본 사용" in get_hwpx_xml_scope_text(background):
        errors.append("사업개요 작성자 메모 제거 실패")
    elif not overview_opening or 'pageBreak="1"' not in overview_opening.group(0):
        errors.append("사업개요 새 쪽 상단 시작 누락")
    background_subheadings = [
        background[start:end]
        for start, end in find_hwpx_tag_spans(background, "hp:p")
        if re.match(r"^ㅇ\s+\([^()]{2,90}\)", get_hwpx_xml_scope_text(background[start:end]).strip())
        and 'charPrIDRef="18"' in background[start:end]
        and 'charPrIDRef="28"' in background[start:end]
        and 'paraPrIDRef="69"' in background[start:end]
        and "<hp:lineBreak/>" in background[start:end]
    ]
    if len(background_subheadings) < 5:
        errors.append(f"사업 추진배경 ㅇ·굵은 소제목·본문 줄바꿈 누락: {len(background_subheadings)}/5")

    spacing_checks = (
        ("Contents/section4.xml", "4. 평가의 한계"),
        ("Contents/section4.xml", "5. 평가팀 구성 및 시행체계"),
        ("Contents/section5.xml", "3. 종합 평가 및 시사점"),
        ("Contents/section7.xml", "(2) 비작동요인"),
    )
    for section_name, heading in spacing_checks:
        if not heading_has_blank_line_before_xml(sections.get(section_name, ""), heading):
            errors.append(f"제목 앞 한 줄 여백 누락: {heading}")

    for section_index in range(2, 9):
        section_name = f"Contents/section{section_index}.xml"
        violations = report_heading_gap_violations_xml(sections.get(section_name, ""))
        if violations:
            errors.append(
                f"제목 역할 기반 한 줄 여백 누락({section_name}): "
                + ", ".join(violations)
            )

    if not spacing_heading_starts_on_fresh_page_xml(
        sections.get("Contents/section4.xml", ""),
        EVALUATION_OVERVIEW_CHAPTER_HEADING,
    ):
        errors.append("PDM 뒤 III. 평가개요 새 페이지 시작 누락")

    theory_section = sections.get("Contents/section8.xml", "")
    if theory_section.count("<hp:pic") != 1:
        errors.append("변화이론 뒤 중복 그림 2개 제거 실패")
    if re.findall(r'binaryItemIDRef="([^"]+)"', theory_section) != ["image1"]:
        errors.append("변화이론 그림 참조가 image1 단일 항목이 아님")
    theory_picture = next(
        (
            theory_section[start:end]
            for start, end in find_hwpx_tag_spans(theory_section, "hp:pic")
        ),
        "",
    )
    theory_picture_paragraph = next(
        (
            theory_section[start:end]
            for start, end in find_hwpx_tag_spans(theory_section, "hp:p")
            if "<hp:pic" in theory_section[start:end]
        ),
        "",
    )
    expected_theory_geometry = (
        f'<hp:orgSz width="{theory_source_width}" height="{theory_source_height}"/>',
        f'<hp:curSz width="{THEORY_IMAGE_FRAME_WIDTH}" height="{THEORY_IMAGE_FRAME_HEIGHT}"/>',
        f'<hc:pt2 x="{theory_source_width}" y="{theory_source_height}"/>',
        f'<hp:imgClip left="0" right="{theory_source_width}" top="0" '
        f'bottom="{theory_source_height}"/>',
        f'<hp:imgDim dimwidth="{theory_source_width}" '
        f'dimheight="{theory_source_height}"/>',
        f'<hp:sz width="{THEORY_IMAGE_FRAME_WIDTH}" widthRelTo="ABSOLUTE" '
        f'height="{THEORY_IMAGE_FRAME_HEIGHT}" heightRelTo="ABSOLUTE" protect="0"/>',
        f'<hp:rotationInfo angle="0" centerX="{THEORY_IMAGE_CENTER_X}" '
        f'centerY="{THEORY_IMAGE_CENTER_Y}" rotateimage="1"/>',
        f'<hc:scaMatrix e1="{THEORY_IMAGE_FRAME_WIDTH / theory_source_width}"',
        'horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER"',
    )
    if theory_picture and not all(token in theory_picture for token in expected_theory_geometry):
        errors.append("변화이론 그림 전체 프레임·원본 비율 정규화 실패")
    picture_opening = re.match(r"<hp:p\b[^>]*>", theory_picture_paragraph)
    if not picture_opening or not all(
        token in picture_opening.group(0)
        for token in (
            f'paraPrIDRef="{THEORY_IMAGE_PARAGRAPH_PARA_PR_ID}"',
            'pageBreak="1"',
        )
    ):
        errors.append("변화이론 그림 전용 가운데 정렬·새 쪽 문단 스타일 불일치")
    page_match = re.search(
        r'<hp:pagePr\b[^>]*\blandscape="([^"]+)"[^>]*\bwidth="(\d+)"'
        r'[^>]*\bheight="(\d+)"[^>]*>.*?'
        r'<hp:margin\b[^>]*\bleft="(\d+)"[^>]*\bright="(\d+)"',
        theory_section,
        re.DOTALL,
    )
    if page_match:
        landscape, page_width, page_height, left_margin, right_margin = page_match.groups()
        rendered_page_width = (
            max(int(page_width), int(page_height))
            if landscape == "NARROWLY"
            else int(page_width)
        )
        body_width = rendered_page_width - int(left_margin) - int(right_margin)
        if body_width != THEORY_LANDSCAPE_BODY_WIDTH:
            errors.append(
                f"변화이론 가로 페이지 본문 폭 불일치: {body_width}/{THEORY_LANDSCAPE_BODY_WIDTH}"
            )
        if THEORY_IMAGE_FRAME_WIDTH > body_width:
            errors.append("변화이론 그림 폭이 가로 A4 본문 폭을 초과함")

    overview_tables = [
        background[start:end]
        for start, end in find_hwpx_tag_spans(background, "hp:tbl")
        if ("사업명(국문)" in get_hwpx_xml_scope_text(background[start:end])
            or "사업 세부내용" in get_hwpx_xml_scope_text(background[start:end]))
    ]
    if not overview_tables:
        errors.append("사업개요 표 누락")
    else:
        overview_position = re.search(r'<hp:pos\b[^>]*/>', overview_tables[0])
        if not overview_position or 'treatAsChar="1"' not in overview_position.group(0):
            errors.append("사업개요 표가 본문 흐름에 고정되지 않음: 앞 사업배경과 겹침 위험")
        margins = re.findall(r"<hp:cellMargin\b[^>]*/>", overview_tables[0])
        expected = str(TABLE_CELL_MARGIN_VERTICAL)
        if not margins or any(
            f'top="{expected}"' not in margin or f'bottom="{expected}"' not in margin
            for margin in margins
        ):
            errors.append("사업개요 표 상하 1pt 셀 여백 불일치")
        for table in overview_tables:
            size = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', table)
            if size and int(size.group(1)) > TABLE_PAGE_BUDGET:
                errors.append("사업개요 표의 한 쪽 높이 한도 초과: 명시적 페이지 분할 필요")

    if any("K-ODAME" in get_hwpx_xml_scope_text(section) for section in sections.values()):
        errors.append("본문 하단 K-ODAME 반복 마크 잔존")

    recommendations = sections.get("Contents/section8.xml", "")
    recommendation_specs = (
        ("환류과제", ("환류과제", "이행부서"), 1, FEEDBACK_ROWS_PER_PAGE, None),
        (
            "교훈",
            ("평가 교훈 분석", "체크리스트"),
            2,
            LESSONS_ROWS_PER_PAGE,
            LESSONS_MAX_TABLE_HEIGHT,
        ),
    )
    for label, needles, header_rows, rows_per_page, max_table_height in recommendation_specs:
        tables = [
            recommendations[start:end]
            for start, end in find_hwpx_tag_spans(recommendations, "hp:tbl")
            if all(token in get_hwpx_xml_scope_text(recommendations[start:end]) for token in needles)
        ]
        if not tables:
            errors.append(f"{label} 표 누락")
            continue
        for table_index, table in enumerate(tables, start=1):
            if "…" in get_hwpx_xml_scope_text(table):
                errors.append(f"{label} {table_index}쪽 셀 생략부호 잔존")
            if any(f'charPrIDRef="{char_id}"' in table for char_id in ("74", "79", "81", "82", "84")):
                errors.append(f"{label} {table_index}쪽 9pt 미만 글자 스타일 잔존")
            rows = find_hwpx_tag_spans(table, "hp:tr")
            if not header_rows < len(rows) <= header_rows + rows_per_page:
                errors.append(
                    f"{label} {table_index}쪽 행 밀도 초과: {len(rows)}/{header_rows + rows_per_page}"
                )
            table_height_match = re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', table)
            if (
                max_table_height
                and table_height_match
                and int(table_height_match.group(1)) > max_table_height
            ):
                errors.append(
                    f"{label} {table_index}쪽 높이 예산 초과: "
                    f"{table_height_match.group(1)}/{max_table_height}"
                )
            if not all(
                attribute in table
                for attribute in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
            ):
                errors.append(f"{label} {table_index}쪽 페이지 안전 정책 불일치")

    criteria_sections = "".join(
        sections.get(name, "")
        for name in ("Contents/section6.xml", "Contents/section7.xml")
    )
    for heading in sorted(FORCED_CRITERION_PAGE_BREAK_LABELS):
        if not heading_starts_on_fresh_page_xml(criteria_sections, heading):
            errors.append(f"기준별 평가결과 새 페이지 시작 누락: {heading}")

    toc = sections.get("Contents/section1.xml", "")
    toc_paragraphs = find_hwpx_all_tag_spans(toc, "hp:p")
    achievement_candidates = [
        (index, start, end)
        for index, (start, end) in enumerate(toc_paragraphs)
        if "Ⅳ. 성과달성도" in get_hwpx_xml_scope_text(toc[start:end])
    ]
    achievement_index = min(
        achievement_candidates,
        key=lambda item: item[2] - item[1],
        default=(-1, -1, -1),
    )[0]
    # Before the first render the official template keeps the dotted leader
    # in the following number-only paragraph. The TOC second pass merges it
    # into the heading. Both are valid at their respective validation stage.
    achievement_toc_scope = "".join(
        toc[start:end]
        for start, end in toc_paragraphs[achievement_index:achievement_index + 2]
    ) if achievement_index >= 0 else ""
    achievement_heading = toc[toc_paragraphs[achievement_index][0]:toc_paragraphs[achievement_index][1]] if achievement_index >= 0 else ""
    achievement_opening = re.match(r"<hp:p\b[^>]*>", achievement_heading)
    fixed_number = re.search(r'<hp:tc\b[^>]*name="toc_number_achievement_page"[^>]*>.*?</hp:tc>', toc, re.S)
    fixed_leader = re.search(r'<hp:tc\b[^>]*name="toc_leader_achievement_page"[^>]*>.*?</hp:tc>', toc, re.S)
    if fixed_number:
        # Native-Hangul-compatible fixed columns supersede the legacy tab.
        number_cell = fixed_number.group()
        style_id = re.search(r'paraPrIDRef="(\d+)"', number_cell)
        style = re.search(r'<hh:paraPr\b(?=[^>]*\bid="' + style_id[1] + r'")[^>]*>.*?</hh:paraPr>', header, re.S) if style_id else None
        if not (style and 'horizontal="RIGHT"' in style.group()
                and re.search(r'<hp:cellSz\b[^>]*width="2200"', number_cell)
                and re.fullmatch(r'\d+', get_hwpx_xml_scope_text(number_cell).strip())
                and fixed_leader and re.fullmatch(r'\.{2,}', get_hwpx_xml_scope_text(fixed_leader.group()).strip())):
            errors.append("목차 성과달성도 고정 열 쪽번호·점선·우측정렬 계약 불일치")
    elif not achievement_toc_scope or not all(
        attribute in achievement_toc_scope for attribute in ('leader="3"', 'type="2"')
    ):
        errors.append("목차 성과달성도 점선 리더 또는 쪽번호 위치 누락")
    elif not achievement_opening or f'paraPrIDRef="{ACHIEVEMENT_TOC_PARA_PR_ID}"' not in achievement_opening.group(0):
        errors.append("목차 성과달성도 문단 스타일 불일치")
    elif re.search(r"<hp:t\b[^>]*>\s*\d+\s*</hp:t>", achievement_heading) and 'width="33800"' not in achievement_heading:
        errors.append("목차 성과달성도 쪽번호 탭 위치 불일치")
    elif re.search(r"<hp:t\b[^>]*>\s*\d+\s*</hp:t>", achievement_heading):
        heading_start, heading_end = toc_paragraphs[achievement_index]
        following_span = next(
            ((start, end) for start, end in toc_paragraphs if start >= heading_end),
            None,
        )
        if following_span:
            following = toc[following_span[0] : following_span[1]]
            following_text = re.sub(r"<[^>]+>", "", get_hwpx_xml_scope_text(following)).strip()
            if not following_text and re.search(r'<hp:tab\b[^>]*\bleader="3"[^>]*/>', following):
                errors.append("목차 성과달성도 아래 빈 점선 행 잔존")

    return {
        "ok": not errors,
        "errors": errors,
        "policy": {
            "chapter": "16pt bold",
            "section": "12pt bold",
            "body": "11pt regular",
            "table_body_minimum": "9pt",
        },
    }


def validate_orphan_heading_page_breaks(data: bytes, headings: set[str]) -> dict:
    """Verify the renderer-selected orphan headings carry RHWP's hard break."""

    errors: list[str] = []
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        sections = [
            archive.read(name).decode("utf-8")
            for name in ("Contents/section6.xml", "Contents/section7.xml")
        ]
    for heading in sorted(headings):
        if not any(heading_starts_on_fresh_page_xml(section, heading) for section in sections):
            errors.append(f"고립 제목 페이지 나눔 누락: {heading}")
    return {"ok": not errors, "errors": errors, "headings": sorted(headings)}
