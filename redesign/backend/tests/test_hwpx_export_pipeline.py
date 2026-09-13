from __future__ import annotations

import json
import unittest
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

from backend.oda_me.hwpx.patchers import (
    GRADE_QUESTION_REASON_CELLS,
    GRADE_SUBTOTAL_REASON_CELLS,
    _toc_labeled_numeric_target,
    achievement_item_fields,
    cleanup_hwpx_placeholder_text_xml,
    find_hwpx_all_tag_spans,
    find_hwpx_tag_spans,
    fit_hwpx_table_value,
    get_hwpx_xml_scope_text,
    hwpx_report_body_lines,
    grade_question_reason,
    normalize_hwpx_manifest_value,
    normalize_project_background_slot,
    normalize_hwpx_report_outline_styles_xml,
    parse_achievement_items,
    parse_feedback_items,
    parse_lesson_items,
    patch_hwpx_achievement_table_xml,
    patch_hwpx_feedback_lessons_tables_xml,
    patch_hwpx_pdm_table_xml,
    patch_hwpx_grade_section_xml,
    patch_hwpx_review_section_slots_xml,
    patch_hwpx_report_outline_header_xml,
    patch_hwpx_summary_ko_document_xml,
    patch_hwpx_section2_toc_page_numbers_xml,
    review_values_for_section,
    replace_hwpx_heading_block_xml,
    repack_hwpx_preserving_original_entries,
    set_hwpx_xml_scope_text,
    section5_summary_paragraph_style,
    style_hwpx_detail_summary_label_xml,
    toc_page_map_from_page_texts,
    trim_hwpx_table_rows_xml,
    validate_section5_summary_xml,
    normalize_hwpx_table_value,
)
from backend.oda_me.hwpx.adapters.contracts import AdapterContractError
from backend.oda_me.hwpx.adapters.summary_ko import (
    SUMMARY_KO_ADAPTER,
    SUMMARY_KO_BLOCKS,
    assert_summary_ko_payload,
    parse_summary_ko_section,
    render_summary_ko_document,
    strip_summary_ko_page_citations,
    validate_summary_ko_manifest,
)
from backend.oda_me.reports.context import sanitize_editor_part_response, structured_slots_to_json
from kodame_intake.hwpx_adapters.summary_ko import compose_summary_ko, summary_fragment as summary_ko_fragment
from kodame_intake.hwpx_pipeline import (
    _background_slots,
    _matrix_slots,
    _pdm_slots,
    _restore_korean_sentence_boundaries,
    _summary_fragment,
    normalize_section_text,
    preserve_structured_grade_section,
)
from kodame_intake.hwpx_layout.headings import (
    _patch_heading_page_breaks_xml,
    force_numbered_criterion_page_breaks_xml,
    heading_starts_on_fresh_page_xml,
    normalize_heading_hierarchy_xml,
    patch_heading_pagination_header_xml,
    style_project_background_subheadings_xml,
)
from kodame_intake.hwpx_layout.rendering import (
    orphan_heading_adjustments_from_analysis,
    validate_render_result,
    validate_summary_page_span,
)
from kodame_intake.hwpx_layout.recommendations import (
    LESSONS_MAX_TABLE_HEIGHT,
    LESSONS_ROWS_PER_PAGE,
    style_recommendation_tables_xml,
)
from report_outline import (
    NARRATIVE_OUTLINE_PART_IDS,
    canonical_narrative_outline_text,
    format_narrative_detail,
    narrative_outline_issues,
)
from kodame_intake.hwpx_layout.grade_table import (
    GRADE_CELL_MARGIN_HORIZONTAL,
    GRADE_CELL_MARGIN_VERTICAL,
    GRADE_HEADER_ROW_HEIGHT,
    GRADE_QUESTION_FONT_HEIGHT,
    GRADE_QUESTION_CELLS,
    GRADE_QUESTION_MAX_HEIGHT,
    GRADE_QUESTION_MIN_HEIGHT,
    GRADE_QUESTION_ROWS,
    GRADE_SUBTOTAL_ROW_HEIGHT,
    GRADE_SUBTOTAL_ROWS,
    GRADE_SUMMARY_ROW_HEIGHT,
    GRADE_SUMMARY_ROWS,
    GRADE_TABLE_PAGE_ROW_GROUPS,
    grade_question_row_height,
    style_grade_table_xml,
)
from kodame_intake.hwpx_layout.tables import (
    ACHIEVEMENT_GROUP_MIN_HEIGHT,
    ACHIEVEMENT_HEADER_ROW_COUNT,
    ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
    ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS,
    EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL,
    EVALUATION_MATRIX_CELL_MARGIN_VERTICAL,
    EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS,
    PDM_TABLE_PAGE_ROW_GROUPS,
    PDM_COLUMN_WIDTHS,
    PDM_MAXIMUM_TABLE_HEIGHT,
    achievement_item_group_height,
    achievement_item_group_physical_heights,
    evaluation_matrix_row_height,
    refresh_evaluation_matrix_split_heights_xml,
    style_achievement_table_xml,
    style_evaluation_matrix_heading_spacing_xml,
    style_evaluation_matrix_table_xml,
    style_pdm_table_xml,
)
from kodame_intake.hwpx_layout.spacing import (
    EVALUATION_OVERVIEW_CHAPTER_HEADING,
    ensure_blank_line_before_headings_xml,
    ensure_blank_line_before_report_headings_xml,
    ensure_page_break_before_heading_xml,
    heading_has_blank_line_before_xml,
    report_heading_gap_violations_xml,
    heading_starts_on_fresh_page_xml as spacing_heading_starts_on_fresh_page_xml,
)
from kodame_intake.hwpx_layout.typography import normalize_report_text_colors_header_xml
from kodame_intake.hwpx_layout.toc import (
    ACHIEVEMENT_TOC_PARA_PR_ID,
    TOC_RIGHT_TAB_PR_ID,
    patch_toc_page_numbers,
    patch_toc_header_layout,
    prune_unexported_appendix_toc_xml,
    normalize_toc_page_number_spacing_xml,
    validate_toc_page_numbers,
)
from kodame_intake.hwpx_layout.theory import attach_feedback_headings_to_table_xml


def paragraph(text: str = "", *, para_pr: str = "75", char_pr: str = "28") -> str:
    text_node = f"<hp:t>{text}</hp:t>" if text else ""
    run = f'<hp:run charPrIDRef="{char_pr}">{text_node}</hp:run>' if text_node else f'<hp:run charPrIDRef="{char_pr}"/>'
    return f'<hp:p id="0" paraPrIDRef="{para_pr}" styleIDRef="0">{run}<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray></hp:p>'


def canonical_summary_document() -> str:
    def detail(topic: str, ordinal: int) -> str:
        return (
            f"{topic}에 관한 {ordinal}번째 세부 판단은 현재 사업에 등록된 자료에서 확인되는 사실을 중심으로 정리하였음. "
            "판단과 근거의 연결을 명확히 하고, 근거가 충분한 범위와 추가 확인이 필요한 범위를 구분하였음. "
            "확인된 내용의 평가적 의미를 사업의 목표와 성과경로에 연결하되 자료가 뒷받침하지 않는 성과는 단정하지 않았음. "
            "남은 근거 공백은 후속 점검에서 확보할 자료와 검증 책임을 구체화해야 하는 과제로 제시하였음."
        )

    def detail_line(topic: str, ordinal: int) -> str:
        if topic in {"사업 기본정보", "주요 성과달성도"}:
            return f"- ({topic[:10]} {ordinal}) {detail(topic, ordinal)}"
        return f"- {detail(topic, ordinal)}"

    blocks = [
        "(1) 대상사업개요",
        "",
        " ㅇ 사업 기본정보",
        *(detail_line("사업 기본정보", index) for index in range(1, 4)),
        "",
        " ㅇ 추진배경 및 주요내용",
        *(detail_line("추진배경 및 주요내용", index) for index in range(1, 4)),
        "",
        "(2) 평가개요",
        "",
        " ㅇ 평가 목적과 범위",
        *(detail_line("평가 목적과 범위", index) for index in range(1, 3)),
        "",
        " ㅇ 평가 방법",
        *(detail_line("평가 방법", index) for index in range(1, 3)),
        "",
        " ㅇ 평가의 한계",
        *(detail_line("평가의 한계", index) for index in range(1, 3)),
        "",
        "(3) 성과달성도",
        "",
        " ㅇ 주요 성과달성도",
        *(detail_line("주요 성과달성도", index) for index in range(1, 7)),
        "",
        "(4) 기준별 평가결과",
    ]
    for criterion in ("적절성", "일관성", "효과성", "효율성", "지속가능성"):
        blocks.append("")
        blocks.append(f" ㅇ {criterion}")
        blocks.extend(detail_line(criterion, index) for index in range(1, 3))
    blocks.extend(("", "(5) 결론"))
    for label in ("종합 결론", "작동요인", "비작동요인", "환류과제 및 교훈"):
        blocks.append("")
        blocks.append(f" ㅇ {label}")
        blocks.extend(detail_line(label, index) for index in range(1, 3))
    return "\n".join(blocks)


class HwpxExportPipelineTests(unittest.TestCase):
    def test_summary_adapter_contract_matches_reviewed_manifest(self) -> None:
        root = Path(__file__).resolve().parents[3]
        manifest = json.loads(
            (root / "hwpx_sections" / "Section5_국문_요약" / "slots.review.json").read_text(encoding="utf-8")
        )
        validate_summary_ko_manifest(manifest)
        self.assertEqual(len(SUMMARY_KO_ADAPTER.slots), 5)
        self.assertEqual(SUMMARY_KO_ADAPTER.hwpx_path, "Contents/section3.xml")
        criteria_slot = next(block for block in SUMMARY_KO_BLOCKS if block.key == "criteria_results")
        self.assertEqual(criteria_slot.min_chars, 1400)
        self.assertEqual(criteria_slot.min_detail_paragraphs, 10)

    def test_summary_adapter_rejects_partial_payload_before_xml_write(self) -> None:
        with self.assertRaises(AdapterContractError):
            assert_summary_ko_payload({"project_overview": " ㅇ 사업 기본정보\n- 사업명: 테스트 사업"})

    def test_summary_page_citations_are_removed_without_deleting_claims(self) -> None:
        source = "성과가 확인되었다 (4차년도 자체평가결과보고서, pp. 5-8). 후속 확인이 필요하다."
        self.assertEqual(
            strip_summary_ko_page_citations(source),
            "성과가 확인되었다. 후속 확인이 필요하다.",
        )

    def test_summary_composer_keeps_saved_draft_reader_text_exact(self) -> None:
        draft = canonical_summary_document()
        result = compose_summary_ko(
            {"project": {"title": "내보내기 단계에서 덮어쓰면 안 되는 이름"}},
            {"summary-ko": draft},
        )
        self.assertEqual(render_summary_ko_document(result.slots), draft)
        self.assertTrue(all(source == ("summary-ko",) for source in result.provenance.values()))
        self.assertEqual(result.fallback_slots, ())

    def test_summary_parser_migrates_legacy_numbers_and_accepts_optional_labels(self) -> None:
        legacy = canonical_summary_document()
        for ordinal in range(1, 6):
            legacy = legacy.replace(f"({ordinal})", f"{ordinal}.")
        rendered = render_summary_ko_document(parse_summary_ko_section(legacy))
        self.assertIn("(1) 대상사업개요", rendered)
        self.assertIn("(5) 결론", rendered)
        self.assertNotIn("1. 대상사업개요", rendered)
        self.assertRegex(rendered, r"(?m)^- [^(].+")
        self.assertRegex(rendered, r"(?m)^- \([^()]+\) .+")

    def test_summary_template_replaces_legacy_outline_and_matches_draft_exact(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        draft = canonical_summary_document()
        slots = parse_summary_ko_section(draft)
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section3.xml").decode("utf-8")
        patched, changed = patch_hwpx_summary_ko_document_xml(xml, slots)
        self.assertGreater(changed, len([line for line in draft.splitlines()]))
        verification = validate_section5_summary_xml(
            patched,
            {"project": {"title": "테스트 농촌 역량강화사업"}},
            {"summary-ko": draft},
        )
        self.assertEqual(verification["block_count"], 5)
        self.assertTrue(verification["text_exact"])
        summary_start = patched.index("(1) 대상사업개요")
        summary_end = patched.index("II. 대상사업개요", summary_start)
        summary_xml = patched[summary_start:summary_end]
        self.assertNotIn("가. 사업명", summary_xml)
        self.assertNotIn("나. 사업개요", summary_xml)
        summary_paragraph_texts = [
            get_hwpx_xml_scope_text(patched[start:end]).strip()
            for start, end in find_hwpx_all_tag_spans(patched, "hp:p")
        ]
        summary_label_index = summary_paragraph_texts.index("1. 국문 요약")
        summary_end_index = summary_paragraph_texts.index("II. 대상사업개요", summary_label_index)
        for index in range(summary_label_index, summary_end_index):
            text = summary_paragraph_texts[index]
            if text == "1. 국문 요약" or text.startswith("ㅇ ") or re.match(r"^\([1-5]\)\s+", text):
                self.assertGreater(index, 0)
                self.assertEqual(summary_paragraph_texts[index - 1], "")
        paragraph_spans = find_hwpx_all_tag_spans(patched, "hp:p")
        for start, end in paragraph_spans[summary_label_index:summary_end_index]:
            paragraph_xml = patched[start:end]
            raw_text = get_hwpx_xml_scope_text(paragraph_xml)
            if raw_text.strip().startswith("- "):
                self.assertTrue(raw_text.startswith("- "), repr(raw_text))
                self.assertNotRegex(raw_text, r"^\s+-\s")
                self.assertRegex(paragraph_xml, r'paraPrIDRef="92"')
        conclusion_paragraph = next(
            patched[start:end]
            for start, end in find_hwpx_all_tag_spans(patched, "hp:p")
            if get_hwpx_xml_scope_text(patched[start:end]).strip() == "(5) 결론"
        )
        self.assertRegex(conclusion_paragraph, r'<hp:p\b[^>]*pageBreak="1"')

    def test_summary_composer_rejects_sparse_fallback_below_four_page_contract(self) -> None:
        with self.assertRaises(AdapterContractError):
            compose_summary_ko(
                {
                    "project": {
                        "title": "테스트 농촌 역량강화사업",
                        "country": "테스트국",
                        "objective": "지역 주민의 자립역량 강화",
                        "period": "2024~2026",
                    },
                    "criteria": [],
                },
                {},
            )

    def test_narrative_sections_share_summary_outline_contract(self) -> None:
        for part_id in NARRATIVE_OUTLINE_PART_IDS:
            normalized = canonical_narrative_outline_text(
                part_id,
                "### 첫 논점\n첫 판단과 근거이다.\n- 세부 한계이다.\n\n나. 둘째 논점\n후속 판단이다.",
            )
            self.assertEqual(narrative_outline_issues(part_id, normalized), [], part_id)
            self.assertNotRegex(normalized, r"(?m)^\s*(?:###|나\.)")
            self.assertRegex(normalized, r"(?m)^ ㅇ 첫 논점$")
            self.assertRegex(normalized, r"(?m)^  - 첫 판단과 근거임\.$")
            self.assertNotIn("세부 판단", normalized)

    def test_narrative_nfkc_keeps_the_reader_facing_circle_marker(self) -> None:
        normalized, _ = normalize_section_text(
            "eval-purpose",
            " ㅇ 평가 목적\n  - 사업의 추진 실태를 점검한다.\n ㅇ 결과 활용\n  - 후속 개선과제를 도출한다.",
        )
        self.assertEqual(
            normalized,
            " ㅇ 평가 목적\n  - 사업의 추진 실태를 점검함.\n"
            " ㅇ 결과 활용\n  - 후속 개선과제를 도출함.",
        )
        self.assertNotIn("ᄋ", normalized)
        self.assertNotRegex(normalized, r"(?m)^\s*-\s+ㅇ\s")

    def test_narrative_section_removes_repeated_fixed_outer_heading(self) -> None:
        normalized, report = normalize_section_text(
            "criteria-other",
            "ㅇ 7. 그 외 평가기준\n"
            "ㅇ 가. 사업 특수성\n"
            "- 현지 응급의료 인력 양성 구조의 확장 가능성을 검토하였다.",
        )
        self.assertNotIn("7. 그 외 평가기준", normalized)
        self.assertEqual(normalized.count("ㅇ 사업 특수성"), 1)
        self.assertNotIn("ㅇ 가.", normalized)
        self.assertGreaterEqual(report["removed_outer_headings"], 1)

    def test_conclusion_removes_roman_numbered_fixed_outer_heading(self) -> None:
        normalized = canonical_narrative_outline_text(
            "conclusion",
            "ㅇ VI. 결론\nㅇ 핵심 성과와 한계\n- 확인된 성과와 남은 한계를 종합한다.",
        )
        self.assertNotIn("ㅇ VI. 결론", normalized)
        self.assertEqual(normalized.count("ㅇ 핵심 성과와 한계"), 1)

    def test_long_outline_detail_remains_one_semantic_paragraph(self) -> None:
        detail = (
            "  - 본 평가는 등록된 사업 문헌을 교차 검토하여 추진 실태를 점검하였다. "
            "협력기관의 역할과 성과 창출 경로도 함께 분석하였다. "
            "후속 연차에는 확인자료를 보완하여 판단의 정확성을 높일 필요가 있다. "
            "세부 지표의 기초선과 목표치는 최신 사업설계매트릭스를 기준으로 대조하였다. "
            "정량 실적은 공식 결과보고서에서 확인된 값만 반영하였다. "
            "자료 공백은 별도 한계로 표시하고 임의 수치로 대체하지 않았다."
        )
        self.assertGreater(len(detail), 180)
        self.assertEqual(hwpx_report_body_lines(detail), [detail])

    def test_summary_render_span_must_be_at_least_four_pages(self) -> None:
        valid = {
            "render": {
                "page_texts": [
                    {"page_number": 6, "text": "1. 국문 요약\n(1) 대상사업개요"},
                    {"page_number": 10, "text": "1. 사업 추진배경"},
                ]
            }
        }
        self.assertEqual(validate_summary_page_span(valid)["rendered_pages"], 4)
        too_short = {
            "render": {
                "page_texts": [
                    {"page_number": 6, "text": "1. 국문 요약\n(1) 대상사업개요"},
                    {"page_number": 9, "text": "1. 사업 추진배경"},
                ]
            }
        }
        with self.assertRaises(RuntimeError):
            validate_summary_page_span(too_short)

    def test_fixed_table_values_remove_inline_markdown_markers(self) -> None:
        self.assertEqual(
            normalize_hwpx_table_value("**달성** · __검토__ · `내부 메모`"),
            "달성 · 검토 · 내부 메모",
        )

    def test_fixed_table_value_uses_a_hard_natural_boundary(self) -> None:
        value = "First core judgment. Second explanation remains in the source database."
        fitted = fit_hwpx_table_value(value, 25)
        self.assertLessEqual(len(fitted), 26)
        self.assertTrue(fitted.startswith("First core judgment."))
        self.assertTrue(fitted.endswith("…"))

    def test_unused_fixed_table_rows_are_removed_and_height_recalculated(self) -> None:
        rows = "".join(
            f'<hp:tr><hp:tc><hp:cellSz width="100" height="{height}"/></hp:tc></hp:tr>'
            for height in (20, 30, 40, 50)
        )
        table = (
            '<hp:tbl rowCnt="4"><hp:sz width="100" height="140"/>'
            + rows
            + "</hp:tbl>"
        )
        trimmed = trim_hwpx_table_rows_xml(table, header_rows=1, data_rows=2)
        self.assertIn('rowCnt="3"', trimmed)
        self.assertIn('height="90"', trimmed)
        self.assertNotIn('height="50"', trimmed)

    def test_pdm_uses_template_cell_addresses_without_truncation(self) -> None:
        labels = {
            0: "프로그램 요약", 1: "객관적 검증지표", 2: "검증수단", 3: "중요가정",
            4: "영향 (Impact)", 9: "성과(Outcome)", 14: "산출물(Outputs)",
            19: "활동(Activities)", 20: "투입(Inputs)", 21: "전제조건 (Pre-conditions)",
        }
        cells = "".join(
            f"<hp:tc>{paragraph(labels.get(index, 'placeholder'), char_pr='29')}</hp:tc>"
            for index in range(25)
        )
        source = f'<hs:sec><hp:tbl pageBreak="NONE" noAdjust="1">{cells}</hp:tbl></hs:sec>'
        slots = {
            "impact_summary": "영향 요약 원문 전체",
            "impact_indicator": "영향 지표 1\n영향 지표 2",
            "impact_mov": "영향 검증수단",
            "impact_assumption": "영향 중요가정",
            "outcome_summary": "성과 요약 원문 전체",
            "outcome_indicator": "성과 지표",
            "outcome_mov": "성과 검증수단",
            "outcome_assumption": "성과 중요가정",
            "outputs_summary": "산출물 요약 원문 전체",
            "outputs_indicator": "산출물 지표",
            "outputs_mov": "산출물 검증수단",
            "outputs_assumption": "산출물 중요가정",
            "activities": "활동 1\n활동 2",
            "inputs": "원본 투입물의 매우 긴 내용도 축약하지 않고 그대로 보존한다",
            "preconditions": "원본 선행조건",
        }
        updated = patch_hwpx_pdm_table_xml(
            source,
            {"pdm": structured_slots_to_json("pdm", slots)},
        )
        table_start, table_end = find_hwpx_tag_spans(updated, "hp:tbl")[0]
        table = updated[table_start:table_end]
        cell_texts = [
            get_hwpx_xml_scope_text(table[start:end]).strip()
            for start, end in find_hwpx_tag_spans(table, "hp:tc")
        ]
        self.assertEqual(cell_texts[5].replace("<hp:lineBreak/>", ""), "영향 지표 1영향 지표 2")
        self.assertEqual(cell_texts[8], slots["impact_summary"])
        self.assertEqual(cell_texts[13], slots["outcome_summary"])
        self.assertEqual(cell_texts[18], slots["outputs_summary"])
        self.assertEqual(cell_texts[22].replace("<hp:lineBreak/>", ""), "활동 1활동 2")
        self.assertEqual(cell_texts[23], slots["inputs"])
        self.assertEqual(cell_texts[24], slots["preconditions"])
        self.assertIn("<hp:lineBreak/>", table)
        self.assertNotIn("…", table)
        self.assertIn("투입(Inputs)", cell_texts[20])
        # The content mapper does not own print typography or pagination.
        self.assertIn('pageBreak="NONE"', table)
        laid_out, changed = style_pdm_table_xml(updated)
        self.assertTrue(changed)
        laid_out_start, laid_out_end = find_hwpx_tag_spans(laid_out, "hp:tbl")[0]
        laid_out_table = laid_out[laid_out_start:laid_out_end]
        self.assertIn('pageBreak="CELL"', laid_out_table)
        self.assertIn('noAdjust="1"', laid_out_table)
        self.assertIn("객관적 검증지표 (OVI)", laid_out_table)
        self.assertIn("검증수단 (MOV)", laid_out_table)
        self.assertIn('charPrIDRef="44"', laid_out_table)
        self.assertIn('charPrIDRef="43"', laid_out_table)
        for legacy_small_style in ('79', '81', '82', '84'):
            self.assertNotIn(f'charPrIDRef="{legacy_small_style}"', laid_out_table)

    def test_pdm_is_compacted_to_one_a4_table_with_merged_input_width(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            source = archive.read("Contents/section4.xml").decode("utf-8")
        slots = {
            "impact_summary": "SDGs 3.6·3.c 연계와 병원 전 응급의료 개선",
            "impact_indicator": "1. 급성기 환자 사망률 감소 / 2. 전문 응급구조사 배치 비율 증가",
            "impact_mov": "보건통계 연보 / 응급의료센터 연례보고서",
            "impact_assumption": "정부 정책 유지 / 채용예산 확보",
            "outcome_summary": "1. 현지 교원 주도 운영 / 2. 자격·취업 연계 / 3. 지역사회 교육 상설화",
            "outcome_indicator": "1-1. 단독 운영 교과목 비율 / 1-2. 표준 교육과정 승인 / 2-1. 졸업시험 합격률 / 2-2. 전공 취업률 / 3-1. 월평균 교육인원",
            "outcome_mov": "학사보고서 / 승인공문 / 자격시험 결과 / 취업조사 / 운영일지",
            "outcome_assumption": "대학 운영재원 확보 / 직역 법적 지위 명문화",
            "outputs_summary": "1. 마스터 교원·표준 교재 / 2. 실습장 / 3. 취업 지원 / 4. CPCR·MCI 훈련",
            "outputs_indicator": "1-1. 인증 교원 수 / 1-2. 교재 종수 / 2-1. 장비 가동률 / 3-1. 매뉴얼 건수 / 3-2. 취업행사 횟수 / 4-1. 강사 수 / 4-2. 합동훈련 횟수",
            "outputs_mov": "연수 결과 / 출판물 / 사용대장 / 매뉴얼 / 행사 결과 / 자격대장 / 훈련 결과",
            "outputs_assumption": "유관기관 협조 / 기자재 유지보수 원활",
            "activities": "1. 현지 교원 모니터링 / 2. 교육과정 인증 / 3. 실습장 유지보수 / 4. CPCR 상설교육 / 5. 직역 제도 컨설팅 / 6. 취업 연계 / 7. 강사 양성 / 8. MCI 합동훈련",
            "inputs": "사업예산 / 교수진 / 재난 전문가 / 현지 교원 / 실습센터 / 합동훈련 장소",
            "preconditions": "1단계 인프라 정상 이관 / 교육부 학과 운영 승인",
        }
        patched = patch_hwpx_pdm_table_xml(
            source,
            {"pdm": structured_slots_to_json("pdm", slots)},
        )
        styled, changed = style_pdm_table_xml(patched)
        self.assertTrue(changed)
        tables = [
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:tbl")
            if all(
                token in get_hwpx_xml_scope_text(styled[start:end])
                for token in ("프로그램 요약", "객관적 검증지표", "중요가정")
            )
        ]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(len(find_hwpx_tag_spans(table, "hp:tr")), 9)
        height = int(re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', table).group(1))
        self.assertLessEqual(height, PDM_MAXIMUM_TABLE_HEIGHT)
        self.assertIn(f'width="{PDM_COLUMN_WIDTHS[1] + PDM_COLUMN_WIDTHS[2]}"', table)
        self.assertIn('charPrIDRef="44"', table)
        self.assertIn('charPrIDRef="43"', table)

    def test_uploaded_pdm_cells_override_generated_report_prose(self) -> None:
        source_slots = {
            "impact_summary": "원본 영향", "impact_indicator": "원본 영향 지표",
            "impact_mov": "원본 영향 MOV", "impact_assumption": "원본 영향 가정",
            "outcome_summary": "원본 성과", "outcome_indicator": "원본 성과 지표",
            "outcome_mov": "원본 성과 MOV", "outcome_assumption": "원본 성과 가정",
            "outputs_summary": "원본 산출", "outputs_indicator": "원본 산출 지표",
            "outputs_mov": "원본 산출 MOV", "outputs_assumption": "원본 산출 가정",
            "activities": "원본 활동", "inputs": "원본 투입", "preconditions": "원본 선행조건",
        }
        generated = (
            "| 구분 | 요약 | 객관적 검증지표 | 검증수단 | 중요가정 |\n"
            "|---|---|---|---|---|\n"
            "| 영향 | 재작성 영향 | 재작성 지표 | 재작성 MOV | 재작성 가정 |"
        )
        slots = _pdm_slots({"_pdm_source_slots": source_slots}, generated, generated)
        self.assertEqual(slots, source_slots)

    def test_empty_template_run_becomes_writable_and_escaped(self) -> None:
        source = paragraph("")
        updated = set_hwpx_xml_scope_text(source, "A&B <검증>")
        self.assertIn("<hp:t>A&amp;B &lt;검증&gt;</hp:t>", updated)
        self.assertNotIn("<hp:linesegarray>", updated)

    def test_adjacent_sections_are_replaced_by_heading_not_paragraph_index(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("1. 적절성", para_pr="15")
            + paragraph("")
            + paragraph("KOICA의 2010년 대 개발도상국 지원전략")
            + paragraph("2. 일관성", para_pr="15")
            + paragraph("")
            + paragraph("네팔 티까품지역 보건의료개선사업과 연계")
            + paragraph("3. 효과성", para_pr="15")
            + paragraph("")
            + paragraph("COIVD-19 과거 예시")
            + "</hs:sec>"
        )
        source, changed = replace_hwpx_heading_block_xml(
            source,
            "1. 적절성",
            "가. 정책 부합성\nCURRENT_RELEVANCE_BODY\n- 근거 간 교차검증을 실시하였다.",
            ["2. 일관성"],
        )
        self.assertEqual(changed, 1)
        source, changed = replace_hwpx_heading_block_xml(
            source,
            "2. 일관성",
            "가. 내적 일관성\nCURRENT_COHERENCE_BODY",
            ["3. 효과성"],
        )
        self.assertEqual(changed, 1)
        source, changed = replace_hwpx_heading_block_xml(
            source,
            "3. 효과성",
            "가. 산출 달성\nCURRENT_EFFECTIVENESS_BODY",
            [],
        )
        self.assertEqual(changed, 1)
        visible = get_hwpx_xml_scope_text(source)
        for expected in (
            "CURRENT_RELEVANCE_BODY",
            "CURRENT_COHERENCE_BODY",
            "CURRENT_EFFECTIVENESS_BODY",
        ):
            self.assertIn(expected, visible)
        for stale in ("KOICA의 2010년", "네팔 티까품지역", "COIVD-19"):
            self.assertNotIn(stale, visible)
        self.assertNotIn('styleIDRef="2"', source)

    def test_hwpx_renderer_defensively_removes_repeated_section_heading_bullet(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("7. 그 외 평가기준", para_pr="15")
            + paragraph("")
            + paragraph("과거 예시 본문")
            + paragraph("IV. 결론", para_pr="15")
            + "</hs:sec>"
        )
        updated, changed = replace_hwpx_heading_block_xml(
            source,
            "7. 그 외 평가기준",
            "ㅇ 7. 그 외 평가기준\n"
            "ㅇ 사업 특수성\n"
            "- 확장 가능성과 제도적 적용 범위를 검토하였다.",
            ["IV. 결론"],
        )
        self.assertEqual(changed, 1)
        visible = get_hwpx_xml_scope_text(updated)
        self.assertEqual(visible.count("7. 그 외 평가기준"), 1)
        self.assertIn("ㅇ 사업 특수성", visible)
        self.assertNotIn("ㅇ 7. 그 외 평가기준", visible)

    def test_narrative_export_restores_template_paragraph_hierarchy(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("1. 평가의 목적과 범위", para_pr="15")
            + paragraph("")
            + paragraph("과거 예시 본문")
            + paragraph("2. 평가매트릭스", para_pr="15")
            + "</hs:sec>"
        )
        updated, changed = replace_hwpx_heading_block_xml(
            source,
            "1. 평가의 목적과 범위",
            "가. 평가의 목적\n현재 자료를 근거로 사업을 평가한다.\nㅇ 판단영역: 적절성\n- 확인자료: 사업계획서",
            ["2. 평가매트릭스"],
        )
        self.assertEqual(changed, 1)
        self.assertIn('paraPrIDRef="67" styleIDRef="0"', updated)
        self.assertIn('paraPrIDRef="71" styleIDRef="0"', updated)
        self.assertIn('paraPrIDRef="69" styleIDRef="0"', updated)
        self.assertIn('paraPrIDRef="92" styleIDRef="0"', updated)
        self.assertIn('charPrIDRef="18"', updated)
        self.assertIn('charPrIDRef="28"', updated)
        self.assertNotIn('charPrIDRef="24"', updated)
        # A real empty paragraph is required after the numbered heading and
        # after ``가.``; an embedded newline alone renders with no visible
        # hierarchy gap in Hancom/rhwp.
        blank_paragraphs = [
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:p")
            if not get_hwpx_xml_scope_text(updated[start:end]).strip()
        ]
        self.assertGreaterEqual(len(blank_paragraphs), 2)
        heading_pos = updated.index("1. 평가의 목적과 범위")
        child_pos = updated.index("가. 평가의 목적")
        body_pos = updated.index("현재 자료를 근거로")
        empty_paragraph_pattern = r'<hp:p\b[^>]*paraPrIDRef="71"[^>]*><hp:run\b[^>]*/>'
        self.assertRegex(updated[heading_pos:child_pos], empty_paragraph_pattern)
        self.assertRegex(updated[child_pos:body_pos], empty_paragraph_pattern)

    def test_each_narrative_circle_heading_has_one_blank_line_above(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("1. 결론", para_pr="15")
            + paragraph("")
            + paragraph("과거 예시 본문")
            + paragraph("2. 작동요인 및 비작동요인", para_pr="15")
            + "</hs:sec>"
        )
        updated, changed = replace_hwpx_heading_block_xml(
            source,
            "1. 결론",
            "ㅇ 핵심 성과와 한계\n"
            "- 주요 성과와 남은 한계를 종합하였다.\n"
            "ㅇ 후속 판단\n"
            "- 다음 단계의 확인사항을 제시하였다.",
            ["2. 작동요인 및 비작동요인"],
        )
        self.assertEqual(changed, 1)
        paragraph_texts = [
            get_hwpx_xml_scope_text(updated[start:end]).strip()
            for start, end in find_hwpx_tag_spans(updated, "hp:p")
        ]
        for label in ("ㅇ 핵심 성과와 한계", "ㅇ 후속 판단"):
            index = paragraph_texts.index(label)
            self.assertEqual(paragraph_texts[index - 1], "")

    def test_parenthetical_detail_labels_are_preserved_even_when_matching_parent(self) -> None:
        lines = hwpx_report_body_lines(
            "ㅇ 추진배경\n- (추진배경) 현재 사업의 배경 본문\n"
            "ㅇ 평가의 목적과 범위\n- (평가목적) 서로 다른 하위 라벨"
        )
        self.assertEqual(lines[1], "  - (추진배경) 현재 사업의 배경 본문")
        self.assertTrue(lines[3].startswith("  - (평가목적)"))

    def test_long_narrative_is_split_at_sentence_boundaries(self) -> None:
        first = "본 평가는 등록된 공식 문헌을 기반으로 당초 의도한 산출물과 성과 달성도를 엄밀히 검토하는 데 목적이 있다."
        second = "사업 추진 과정에서 확인된 제도화, 교육과정, 실습환경과 현지 교원 역량강화 실적을 종합적으로 점검한다."
        third = "이를 통해 학과 운영의 자립성 제고와 성과 확산을 위한 환류과제를 도출하고 유사 사업의 발전적 모델을 제시한다."
        source = " ".join([first, second, third])
        lines = hwpx_report_body_lines(source)
        self.assertGreaterEqual(len(lines), 2)
        self.assertEqual(" ".join(lines), source)
        self.assertTrue(all(line.endswith(".") for line in lines))

    def test_long_detail_is_split_into_labeled_semantic_paragraphs(self) -> None:
        sentences = [
            "공식 사업문서와 연차별 실적을 대조하여 교육과정 및 실습환경 구축 진척을 확인하였음.",
            "학과 승인과 국가 직무코드 확보는 제도화 측면의 핵심 성과로 평가됨.",
            "다만 졸업생 취업률과 현장 서비스 변화는 성과 산정시점이 도래하지 않아 보수적으로 판단하였음.",
            "후속 모니터링에서는 성별·지역별 분리통계와 자격시험 및 취업 실적을 같은 지표대장으로 갱신할 필요가 있음.",
            "장기성과는 현지 기관의 공식 통계와 추적조사를 결합해 검증할 필요가 있음.",
        ]
        source = "ㅇ 산출 및 성과 달성\n- (산출·성과 진척) " + " ".join(sentences * 2)
        normalized = canonical_narrative_outline_text("criteria-effectiveness", source)
        detail_lines = [line for line in normalized.splitlines() if line.strip().startswith("-")]
        self.assertGreaterEqual(len(detail_lines), 2)
        self.assertTrue(detail_lines[0].strip().startswith("- (산출·성과 진척)"))
        self.assertTrue(all(not line.strip().startswith("- (") for line in detail_lines[1:]))
        visible = " ".join(
            re.sub(r"^\s*-\s+(?:\([^)]*\)\s+)?", "", line)
            for line in detail_lines
        )
        self.assertEqual(" ".join(sentences * 2), visible)
        self.assertEqual(narrative_outline_issues("criteria-effectiveness", normalized), [])

    def test_detail_paragraph_style_has_configured_after_spacing(self) -> None:
        source = (
            '<hh:paraPr id="92"><hp:switch>'
            '<hp:case><hh:margin><hc:intent value="-1"/><hc:left value="1"/>'
            '<hc:next value="0"/></hh:margin></hp:case>'
            '<hp:default><hh:margin><hc:intent value="-1"/><hc:left value="1"/>'
            '<hc:next value="0"/></hh:margin></hp:default>'
            '</hp:switch></hh:paraPr>'
        )
        updated = patch_hwpx_report_outline_header_xml(source)
        self.assertEqual(updated.count('<hc:next value="300"/>'), 2)

    def test_summary_blocks_normalize_markers_and_remove_markdown(self) -> None:
        self.assertEqual(
            normalize_hwpx_manifest_value(
                5,
                "project_overview",
                "○ **사업 기본정보**\n- 사업명: 테스트 사업",
            ),
            " ㅇ 사업 기본정보\n- 사업명: 테스트 사업",
        )
        self.assertEqual(
            normalize_hwpx_manifest_value(
                5,
                "criteria_results",
                "ㅇ 적절성\n- (협력·조정) 정책 및 기관 간 정합성이 확인되었음.",
            ),
            " ㅇ 적절성\n- 정책 및 기관 간 정합성이 확인되었음.",
        )
        self.assertEqual(
            normalize_hwpx_manifest_value(
                5,
                "achievement",
                "ㅇ 주요 성과달성도\n- (확인된 달성) 공식 실적이 확인되었음.",
            ),
            " ㅇ 주요 성과달성도\n- (확인된 달성) 공식 실적이 확인되었음.",
        )

    def test_korean_report_sentence_boundaries_are_restored(self) -> None:
        source = "사업 목적에 부합한다 아울러 자료를 교차 검토하였다 향후 추적조사가 필요하다"
        restored = _restore_korean_sentence_boundaries(source)
        self.assertEqual(
            restored,
            "사업 목적에 부합한다. 아울러 자료를 교차 검토하였다. 향후 추적조사가 필요하다",
        )

    def test_joined_parent_and_section_heading_is_removed(self) -> None:
        normalized, report = normalize_section_text(
            "eval-team",
            "### III. 평가개요 | 5. 평가팀 구성 및 시행체계\n"
            "### 평가팀 구성 및 인력별 역할\n"
            "평가팀은 역할을 분담한다.",
        )
        self.assertNotIn("III. 평가개요", normalized)
        self.assertNotIn("5. 평가팀 구성 및 시행체계", normalized)
        self.assertIn(" ㅇ 평가팀 구성 및 인력별 역할", normalized)
        self.assertIn("  - 평가팀은 역할을 분담함.", normalized)
        self.assertGreaterEqual(report["removed_outer_headings"], 1)

    def test_effectiveness_detail_preserves_optional_label_and_nominal_endings(self) -> None:
        normalized = canonical_narrative_outline_text(
            "criteria-effectiveness",
            "ㅇ 산출 및 성과 달성\n"
            "- 2022년부터 사업 산출 및 성과 달성을 추진하고 있다. 문헌 검토 결과 일정한 진척이 확인된다.",
        )
        self.assertIn("  - 2022년부터", normalized)
        self.assertIn("추진하고 있음.", normalized)
        self.assertIn("확인됨.", normalized)
        self.assertNotRegex(normalized, r"(?:있다|확인된다)\.")

    def test_crosscutting_generic_labels_are_omitted_without_rewriting_claims(self) -> None:
        normalized = canonical_narrative_outline_text(
            "criteria-crosscutting",
            "ㅇ 젠더·인권·취약계층 고려\n"
            "- (후속 과제) 본 사업은 의료 소외 계층의 응급의료 접근성을 향상시키는 방향으로 설계되었음. "
            "참여 과정에서 동등한 기회를 보장하는 운영 지침을 정비할 필요가 있음.\n"
            "- (후속 과제) 수혜자 분리 통계 관리 체계를 마련하고 연도별 참여 인원의 "
            "성별·계층별 현황을 기록할 수 있는 서식을 정비해야 함.",
        )
        self.assertIn("  - 본 사업은 의료 소외 계층의", normalized)
        self.assertIn("  - 수혜자 분리 통계 관리 체계를", normalized)
        self.assertNotIn("(후속 과제)", normalized)
        self.assertEqual(narrative_outline_issues("criteria-crosscutting", normalized), [])

    def test_unmarked_wrapped_sentences_continue_the_same_dash_paragraph(self) -> None:
        normalized = canonical_narrative_outline_text(
            "criteria-crosscutting",
            "ㅇ 젠더·인권·취약계층 고려\n"
            "- (포용적 설계) 취약계층의 접근성을 고려하여 사업을 설계하였음.\n"
            "또한 모든 참여자에게 동등한 기회를 제공하도록 운영 원칙을 마련하였음.",
        )
        self.assertEqual(normalized.count("  - "), 1)
        self.assertIn("운영 원칙을 마련하였음.", normalized)

    def test_duplicate_detail_labels_are_reported_within_one_parent(self) -> None:
        issues = narrative_outline_issues(
            "criteria-crosscutting",
            " ㅇ 젠더·인권·취약계층 고려\n"
            "  - (후속 과제) 첫 번째 보완사항을 정리함.\n"
            "  - (후속 과제) 두 번째 보완사항을 정리함.",
        )
        self.assertTrue(any("요약어 '후속 과제'이 중복" in issue for issue in issues))

    def test_hwpx_detail_summary_label_is_bold_without_changing_visible_text(self) -> None:
        source = paragraph("- (산출·성과 진척) 확인된 실적을 종합함.")
        styled = style_hwpx_detail_summary_label_xml(source)
        self.assertEqual(get_hwpx_xml_scope_text(styled), "- (산출·성과 진척) 확인된 실적을 종합함.")
        runs = re.findall(r'<hp:run\b[^>]*charPrIDRef="(\d+)"[^>]*>(.*?)</hp:run>', styled)
        self.assertEqual([item[0] for item in runs], ["28", "18", "28"])
        self.assertEqual(get_hwpx_xml_scope_text(runs[1][1]), "(산출·성과 진척)")

    def test_generated_korean_outline_uses_standard_order(self) -> None:
        normalized, _ = normalize_section_text(
            "criteria-other",
            "### 첫 번째 판단\n본문 1\n### 두 번째 판단\n본문 2\n### 세 번째 판단\n본문 3",
        )
        self.assertIn(" ㅇ 첫 번째 판단", normalized)
        self.assertIn(" ㅇ 두 번째 판단", normalized)
        self.assertIn(" ㅇ 세 번째 판단", normalized)
        self.assertNotIn("까. ", normalized)

    def test_conclusion_chapter_number_follows_performance_and_criteria(self) -> None:
        cleaned = cleanup_hwpx_placeholder_text_xml(paragraph("IV. 결론"))
        self.assertIn("VI. 결론", cleaned)
        self.assertNotIn("IV. 결론", cleaned)

    def test_achievement_guidance_cell_is_short_enough_for_fixed_column(self) -> None:
        texts = [
            "성과지표" if index == 1 else
            "기초선" if index == 7 else
            "달성도" if index == 4 else
            "(e)PDM 내 주요 산출물(output)/ * 달성도 추적 가능 시 성과(outcome) 기재" if index == 11 else
            f"cell-{index}"
            for index in range(20)
        ]
        table = "<hp:tbl><hp:tr>" + "".join(
            f"<hp:tc>{paragraph(value)}</hp:tc>" for value in texts
        ) + "</hp:tr></hp:tbl>"
        updated = patch_hwpx_achievement_table_xml(table, {"achievement": ""})
        self.assertIn("주요 산출물·성과", updated)
        self.assertNotIn("달성도 추적 가능 시", updated)

    def test_export_preserves_saved_matrix_questions_despite_new_evaluation(self) -> None:
        raw = (
            "| 평가기준 | 평가질문 | 측정지표 | 자료출처 | 분석방법 |\n"
            "|---|---|---|---|---|\n"
            "| 적절성 | 사업은 경제적이고 시의적절한 방식으로 추진되었는가? | 과거 지표 | 과거 자료 | 문헌검토 |"
        )
        evaluations = [{
            "id": "relevance",
            "evaluationResult": {
                "questionAssessments": [{"question": "사업 설계가 수원국 정책과 실제 수요에 부합하는가?"}]
            },
        }]
        slots = _matrix_slots(raw, evaluations)
        self.assertEqual(slots["relevance_question"], "사업은 경제적이고 시의적절한 방식으로 추진되었는가?")

    def test_feedback_markdown_table_keeps_all_rows(self) -> None:
        raw = (
            "| 구분 | 제언 | 이해관계자 | 선정 사유 | 후속 확인자료 |\n"
            "|---|---|---|---|---|\n"
            "| 사업관리 | 조치 1 | 수행기관 | 사유 1 | 자료 1 |\n"
            "| 사업모델 | 조치 2 | 수원기관 | 사유 2 | 자료 2 |\n"
            "| 성과관리 | 조치 3 | 평가팀 | 사유 3 | 자료 3 |\n"
            "| 제도개선 | 조치 4 | 관계부처 | 사유 4 | 자료 4 |"
        )
        rows = parse_feedback_items(raw)
        self.assertEqual([row["task"] for row in rows], ["조치 1", "조치 2", "조치 3", "조치 4"])
        self.assertTrue(all("우선순위:" in row["reason"] for row in rows))
        self.assertTrue(all("완료기한:" in row["opinion"] and "점검주기:" in row["opinion"] for row in rows))

    def test_feedback_extended_markdown_fields_are_preserved(self) -> None:
        raw = (
            "| 구분 | 제언 | 이해관계자 | 선정 사유 | 우선순위 | 완료기한 | 점검주기 | 후속 확인자료 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 성과관리 | 지표를 갱신한다 | 수행기관 | 연차별 오차 방지 | 상 | 2026.12.31 | 월 | 지표대장·회의록 |"
        )
        rows = parse_feedback_items(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["priority"], "상")
        self.assertEqual(rows[0]["due_date"], "2026.12.31")
        self.assertEqual(rows[0]["review_cycle"], "월")
        self.assertIn("지표대장·회의록", rows[0]["opinion"])

    def test_feedback_headings_remain_visible_paragraphs_before_table(self) -> None:
        chapter = (
            '<hp:p id="1" paraPrIDRef="15" styleIDRef="2" pageBreak="0">'
            '<hp:run charPrIDRef="76"><hp:t>3. 환류과제 및 교훈</hp:t></hp:run></hp:p>'
        )
        subsection = (
            '<hp:p id="2" paraPrIDRef="15" styleIDRef="2" pageBreak="0">'
            '<hp:run charPrIDRef="76"><hp:t>(1) 환류과제</hp:t></hp:run></hp:p>'
        )
        table = (
            '<hp:p id="3" paraPrIDRef="64" styleIDRef="25" pageBreak="1">'
            '<hp:run charPrIDRef="62"><hp:tbl>'
            '<hp:t>평가 시 관찰사항 환류과제 이행부서</hp:t>'
            '</hp:tbl></hp:run></hp:p>'
        )
        updated, changed = attach_feedback_headings_to_table_xml(
            f'<hs:sec>{chapter}{subsection}{table}</hs:sec>'
        )
        self.assertTrue(changed)
        paragraphs = [
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:p")
        ]
        chapter_paragraph = next(item for item in paragraphs if "3. 환류과제 및 교훈" in item)
        subsection_paragraph = next(item for item in paragraphs if "(1) 환류과제" in item)
        table_paragraph = next(item for item in paragraphs if "<hp:tbl" in item)
        self.assertNotIn("<hp:tbl", chapter_paragraph)
        self.assertNotIn("<hp:tbl", subsection_paragraph)
        self.assertIn('pageBreak="1"', chapter_paragraph)
        self.assertIn('pageBreak="0"', subsection_paragraph)
        self.assertIn('pageBreak="0"', table_paragraph)
        self.assertLess(updated.index("3. 환류과제 및 교훈"), updated.index("<hp:tbl"))

    def test_mechanical_truncated_detail_label_is_replaced_from_content(self) -> None:
        formatted = format_narrative_detail(
            "(추진배경및주요내 제약) 현지 교원 연수와 표준 교육과정을 통해 독자 운영 역량을 강화하였음.",
            "추진배경 및 주요내용",
            2,
        )
        self.assertEqual(formatted, "현지 교원 연수와 표준 교육과정을 통해 독자 운영 역량을 강화하였음.")
        self.assertNotIn("추진배경및주요내", formatted)

    def test_toc_second_pass_writes_page_into_cleared_text_node(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section1.xml").decode("utf-8")
        first, _ = patch_hwpx_section2_toc_page_numbers_xml(xml, {})
        second, changed = patch_hwpx_section2_toc_page_numbers_xml(
            first,
            {"summary_ko_page": "4", "project_background_page": "7"},
        )
        self.assertGreaterEqual(changed, 2)
        self.assertRegex(second, r"<hp:t>\s*4\s*</hp:t>")
        self.assertRegex(second, r"<hp:t>\s*7\s*</hp:t>")
        third, changed = patch_hwpx_section2_toc_page_numbers_xml(
            second,
            {"summary_ko_page": "5", "project_background_page": "8"},
        )
        self.assertGreaterEqual(changed, 2)
        self.assertRegex(third, r"<hp:t>\s*5\s*</hp:t>")
        self.assertRegex(third, r"<hp:t>\s*8\s*</hp:t>")

    def test_toc_page_numbers_have_no_template_padding(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        page_map = {
            "evaluation_team_page": "23",
            "criteria_sustainability_page": "41",
        }
        updated, _ = patch_toc_page_numbers(template.read_bytes(), page_map)
        with zipfile.ZipFile(BytesIO(updated), "r") as archive:
            xml = archive.read("Contents/section1.xml").decode("utf-8")
        for label, expected in (
            ("5. 평가팀 구성 및 시행체계", "23"),
            ("5. 지속가능성", "41"),
        ):
            target = _toc_labeled_numeric_target(xml, label)
            self.assertIsNotNone(target, label)
            self.assertEqual(target[3].group(2), expected, label)
        validation = validate_toc_page_numbers(updated, page_map)
        self.assertTrue(validation["ok"], validation["mismatches"])

    def test_toc_spacing_normalizer_repairs_padded_page_nodes(self) -> None:
        xml = (
            '<hp:p paraPrIDRef="53"><hp:run charPrIDRef="80"><hp:t>'
            '5. 평가팀 구성 및 시행체계<hp:tab width="27056" leader="3" type="2"/>'
            '</hp:t></hp:run><hp:run charPrIDRef="61"><hp:t> 23 </hp:t></hp:run></hp:p>'
        )
        updated, changed = normalize_toc_page_number_spacing_xml(xml)
        self.assertEqual(changed, 1)
        self.assertIn('<hp:t>23</hp:t>', updated)
        self.assertNotIn('<hp:t> 23 </hp:t>', updated)

    def test_toc_stabilized_pass_keeps_feedback_page_distinct_from_achievement(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        page_map = {"achievement_page": "20", "feedback_lessons_page": "48"}
        first, _ = patch_toc_page_numbers(template.read_bytes(), page_map)
        stabilized, _ = patch_toc_page_numbers(first, page_map)
        validation = validate_toc_page_numbers(stabilized, page_map)
        self.assertTrue(validation["ok"], validation["mismatches"])
        self.assertEqual(validation["actual"]["achievement_page"], "20")
        self.assertEqual(validation["actual"]["feedback_lessons_page"], "48")

    def test_toc_removes_template_appendix_rows_when_no_appendix_is_exported(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section1.xml").decode("utf-8")
        self.assertIn("첨부", get_hwpx_xml_scope_text(xml))
        updated, changed = prune_unexported_appendix_toc_xml(xml, {})
        self.assertEqual(changed, 1)
        visible = get_hwpx_xml_scope_text(updated)
        self.assertNotIn("첨부", visible)
        self.assertNotIn("평가결과 영문 요약", visible)
        self.assertNotIn("참고문헌 목록", visible)

    def test_achievement_toc_chapter_style_uses_official_right_tab(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            header = archive.read("Contents/header.xml").decode("utf-8")
        updated, changed = patch_toc_header_layout(header)
        self.assertTrue(changed)
        paragraph_style = re.search(
            rf'<hh:paraPr\b(?=[^>]*\bid="{ACHIEVEMENT_TOC_PARA_PR_ID}")[^>]*>',
            updated,
        )
        self.assertIsNotNone(paragraph_style)
        self.assertIn(f'tabPrIDRef="{TOC_RIGHT_TAB_PR_ID}"', paragraph_style.group(0))
        repeated, changed = patch_toc_header_layout(updated)
        self.assertFalse(changed)
        self.assertEqual(repeated, updated)

    def test_toc_preserves_leaders_and_keeps_achievement_page_on_heading(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section1.xml").decode("utf-8")
        first, _ = patch_hwpx_section2_toc_page_numbers_xml(xml, {})
        second, _ = patch_hwpx_section2_toc_page_numbers_xml(first, {"achievement_page": "18"})
        self.assertIn('leader="3"', second)
        achievement_paragraph = next(
            second[start:end]
            for start, end in find_hwpx_tag_spans(second, "hp:p")
            if "Ⅳ. 성과달성도" in second[start:end]
        )
        self.assertIn('<hp:tab width="33800" leader="3" type="2"/>', achievement_paragraph)
        self.assertIn("<hp:t>18</hp:t>", achievement_paragraph)
        self.assertIn("<hp:linesegarray>", achievement_paragraph)
        self.assertRegex(
            achievement_paragraph,
            r'charPrIDRef="78"[^>]*><hp:t>Ⅳ\. 성과달성도<hp:tab width="33800" leader="3" type="2"/>',
        )
        toc_spans = find_hwpx_all_tag_spans(second, "hp:p")
        achievement_span = min(
            ((start, end) for start, end in toc_spans if "Ⅳ. 성과달성도" in second[start:end]),
            key=lambda span: span[1] - span[0],
        )
        following_span = next((start, end) for start, end in toc_spans if start >= achievement_span[1])
        following_paragraph = second[following_span[0] : following_span[1]]
        self.assertNotIn("<hp:tab", following_paragraph)
        self.assertEqual(get_hwpx_xml_scope_text(following_paragraph).strip(), "")
        third, changed = patch_hwpx_section2_toc_page_numbers_xml(second, {"achievement_page": "15"})
        self.assertGreaterEqual(changed, 1)
        achievement_paragraph = next(
            third[start:end]
            for start, end in find_hwpx_tag_spans(third, "hp:p")
            if "Ⅳ. 성과달성도" in third[start:end]
        )
        self.assertIn("<hp:t>15</hp:t>", achievement_paragraph)

        without_leader = achievement_paragraph.replace('<hp:run charPrIDRef="83"><hp:t><hp:tab width="33800" leader="3" type="2"/></hp:t></hp:run>', "")
        damaged = third.replace(achievement_paragraph, without_leader)
        repaired, changed = patch_hwpx_section2_toc_page_numbers_xml(damaged, {"achievement_page": "16"})
        self.assertGreaterEqual(changed, 1)
        repaired_paragraph = next(
            repaired[start:end]
            for start, end in find_hwpx_tag_spans(repaired, "hp:p")
            if "Ⅳ. 성과달성도" in repaired[start:end]
        )
        self.assertIn('<hp:tab width="33800" leader="3" type="2"/>', repaired_paragraph)
        self.assertIn("<hp:t>16</hp:t>", repaired_paragraph)

    def test_toc_sync_removes_reintroduced_blank_achievement_leader_row(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section1.xml").decode("utf-8")
        cleared, _ = patch_hwpx_section2_toc_page_numbers_xml(xml, {})
        cleared_spans = find_hwpx_all_tag_spans(cleared, "hp:p")
        cleared_heading = min(
            ((start, end) for start, end in cleared_spans if "Ⅳ. 성과달성도" in cleared[start:end]),
            key=lambda span: span[1] - span[0],
        )
        blank_leader_span = next((start, end) for start, end in cleared_spans if start >= cleared_heading[1])
        blank_leader = cleared[blank_leader_span[0] : blank_leader_span[1]]
        self.assertEqual(re.sub(r"<[^>]+>", "", get_hwpx_xml_scope_text(blank_leader)).strip(), "")
        self.assertIn('leader="3"', blank_leader)

        populated, _ = patch_hwpx_section2_toc_page_numbers_xml(cleared, {"achievement_page": "17"})
        populated_spans = find_hwpx_all_tag_spans(populated, "hp:p")
        populated_heading = min(
            ((start, end) for start, end in populated_spans if "Ⅳ. 성과달성도" in populated[start:end]),
            key=lambda span: span[1] - span[0],
        )
        damaged = populated[: populated_heading[1]] + blank_leader + populated[populated_heading[1] :]

        repaired, changed = patch_hwpx_section2_toc_page_numbers_xml(damaged, {"achievement_page": "18"})
        self.assertGreaterEqual(changed, 1)
        repaired_spans = find_hwpx_all_tag_spans(repaired, "hp:p")
        repaired_heading = min(
            ((start, end) for start, end in repaired_spans if "Ⅳ. 성과달성도" in repaired[start:end]),
            key=lambda span: span[1] - span[0],
        )
        following_span = next((start, end) for start, end in repaired_spans if start >= repaired_heading[1])
        following = repaired[following_span[0] : following_span[1]]
        self.assertNotIn("<hp:tab", following)
        self.assertIn("<hp:t>18</hp:t>", repaired[repaired_heading[0] : repaired_heading[1]])

    def test_repack_preserves_all_generated_report_visual_bytes(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        output = BytesIO()
        generated = {
            "BinData/image1.png": b"\x89PNG\r\n\x1a\ncurrent-theory-visual",
            "BinData/image2.bmp": b"BMcurrent-grade-overview",
            "BinData/image3.bmp": b"BMcurrent-performance-overview",
        }
        with zipfile.ZipFile(template, "r") as source, zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                raw = generated.get(info.filename, source.read(info.filename))
                target.writestr(info, raw)
        repacked = repack_hwpx_preserving_original_entries(output.getvalue())
        with zipfile.ZipFile(BytesIO(repacked), "r") as archive:
            for name, expected in generated.items():
                self.assertEqual(archive.read(name), expected, name)

    def test_summary_fragment_drops_source_heading_page_citation_and_status_code(self) -> None:
        result = _summary_fragment(
            "1. 개발문제와 사업 필요성 사업은 ongoing 상태이다 (1차년도 사업계획서, p. 7).",
            200,
        )
        self.assertFalse(result.startswith("1."))
        self.assertNotIn("p. 7", result)
        self.assertIn("진행 중", result)

    def test_summary_method_compaction_never_splits_a_project_period(self) -> None:
        source = (
            "본 평가는 대한민국 정부 지원 사업의 운영 실태와 성과를 객관적이고 체계적으로 검증하기 위해 수행되었다. "
            "본 사업은 진행 중 상태의 84개월(2022. 04. 01. ~2029. 03. 31.) 장기 프로젝트이므로 현재 시점의 성과를 점검하였다."
        )
        result = summary_ko_fragment(source, 120)
        self.assertEqual(result, "본 평가는 대한민국 정부 지원 사업의 운영 실태와 성과를 객관적이고 체계적으로 검증하기 위해 수행되었다.")
        self.assertEqual(result.count("("), result.count(")"))

    def test_summary_slots_use_fixed_three_level_paragraph_styles(self) -> None:
        self.assertEqual(section5_summary_paragraph_style("project_overview"), 67)
        self.assertEqual(section5_summary_paragraph_style("evaluation_overview"), 67)
        self.assertEqual(section5_summary_paragraph_style("conclusion"), 67)

    def test_summary_outline_is_forced_to_parent_bullet_detail_alignment(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("나. 사업개요", para_pr="3", char_pr="3")
            + paragraph("ㅇ 추진개요", para_pr="85", char_pr="5")
            + paragraph("  - 개발문제와 사업 필요성", para_pr="86", char_pr="5")
            + "</hs:sec>"
        )
        updated, changed = normalize_hwpx_report_outline_styles_xml(source)
        self.assertEqual(changed, 3)
        self.assertRegex(updated, r'paraPrIDRef="67" styleIDRef="0"[^>]*><hp:run charPrIDRef="18"')
        self.assertRegex(updated, r'paraPrIDRef="69" styleIDRef="0"[^>]*><hp:run charPrIDRef="28"')
        self.assertRegex(updated, r'paraPrIDRef="92" styleIDRef="0"[^>]*><hp:run charPrIDRef="28"')
        detail_paragraph = next(
            updated[start:end]
            for start, end in find_hwpx_all_tag_spans(updated, "hp:p")
            if get_hwpx_xml_scope_text(updated[start:end]).strip().startswith("-")
        )
        self.assertEqual(get_hwpx_xml_scope_text(detail_paragraph), "- 개발문제와 사업 필요성")

    def test_template_indent_contract_hangs_detail_continuation_after_dash(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            header = ET.fromstring(
                patch_hwpx_report_outline_header_xml(archive.read("Contents/header.xml").decode("utf-8"))
            )

        def branch_margin(para_pr_id: int, branch_name: str) -> tuple[int, int]:
            paragraph = next(
                node
                for node in header.iter()
                if node.tag.endswith("}paraPr") and node.attrib.get("id") == str(para_pr_id)
            )
            branch = next(node for node in paragraph.iter() if node.tag.endswith(f"}}{branch_name}"))
            left = next(node for node in branch.iter() if node.tag.endswith("}left"))
            intent = next(node for node in branch.iter() if node.tag.endswith("}intent"))
            return int(left.attrib["value"]), int(intent.attrib["value"])

        bullet_left, bullet_intent = branch_margin(69, "case")
        detail_left, detail_intent = branch_margin(92, "case")
        detail_default_left, detail_default_intent = branch_margin(92, "default")
        self.assertEqual(bullet_left, 1831)
        self.assertEqual(bullet_left + bullet_intent, 831)
        self.assertEqual(detail_left, 4831)
        self.assertEqual(detail_intent, -1000)
        self.assertEqual(detail_left + detail_intent, 3831)
        self.assertEqual(detail_default_left, 9662)
        self.assertEqual(detail_default_intent, -2000)
        self.assertEqual(detail_default_left + detail_default_intent, 7662)
        self.assertGreater(detail_left, bullet_left)
        self.assertGreater(detail_left, detail_left + detail_intent)

    def test_layout_contract_normalizes_chapter_section_and_page_cohesion(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            header = archive.read("Contents/header.xml").decode("utf-8")
        header = patch_heading_pagination_header_xml(header)
        for para_id in (15, 31, 67, 69):
            paragraph_property = re.search(
                rf'<hh:paraPr\b[^>]*\bid="{para_id}"[^>]*>.*?</hh:paraPr>',
                header,
                re.DOTALL,
            ).group(0)
            self.assertIn('keepWithNext="1"', paragraph_property)
        for para_id in (71, 92):
            paragraph_property = re.search(
                rf'<hh:paraPr\b[^>]*\bid="{para_id}"[^>]*>.*?</hh:paraPr>',
                header,
                re.DOTALL,
            ).group(0)
            self.assertIn('widowOrphan="1"', paragraph_property)

        source = (
            "<hs:sec>"
            + paragraph("VI. 결론", para_pr="44", char_pr="41")
            + paragraph("3. 효과성", para_pr="15", char_pr="28")
            + "</hs:sec>"
        )
        updated, stats = normalize_heading_hierarchy_xml(source)
        self.assertEqual(stats.major_chapters, 1)
        self.assertEqual(stats.section_headings, 1)
        self.assertRegex(updated, r'paraPrIDRef="31"[^>]*>.*?charPrIDRef="63"')
        self.assertRegex(updated, r'paraPrIDRef="15"[^>]*>.*?charPrIDRef="76"')

        moved, changed = _patch_heading_page_breaks_xml(updated, {"3. 효과성"})
        self.assertEqual(changed, 1)
        self.assertRegex(moved, r'paraPrIDRef="15"[^>]*pageBreak="1"[^>]*>.*?3. 효과성')
        self.assertTrue(heading_starts_on_fresh_page_xml(moved, "3. 효과성"))

    def test_first_render_moves_only_a_heading_orphan_and_corrects_its_toc_page(self) -> None:
        analysis = {
            "render": {
                "page_texts": [
                    {"page_number": 25, "text": "2. 일관성\n충분한 본문 " + ("가" * 300)},
                    {"page_number": 26, "text": ("선행 문단 " * 80) + "3. 효과성"},
                    {"page_number": 29, "text": "4. 효율성\n본문이 이어진다."},
                ]
            }
        }
        headings, corrections, evidence = orphan_heading_adjustments_from_analysis(analysis)
        self.assertEqual(headings, {"3. 효과성"})
        self.assertEqual(corrections, {"criteria_effectiveness_page": "27"})
        self.assertEqual(evidence[0]["trailing_chars"], 0)

    def test_achievement_layout_raises_legacy_eight_point_styles(self) -> None:
        cells = ''.join(
            f'<hp:tc>{paragraph(text, para_pr="38", char_pr=char_pr)}</hp:tc>'
            for text, char_pr in [
                ("성과지표", "43"), ("기초선", "44"), ("달성도", "44"),
                *[(f"값 {index}", "44") for index in range(30)],
            ]
        )
        source = f'<hs:sec><hp:tbl pageBreak="CELL" repeatHeader="0" noAdjust="1">{cells}</hp:tbl></hs:sec>'
        updated, changed = style_achievement_table_xml(source)
        self.assertTrue(changed)
        self.assertNotIn('charPrIDRef="43"', updated)
        self.assertNotIn('charPrIDRef="44"', updated)
        self.assertIn('charPrIDRef="85"', updated)
        self.assertIn('charPrIDRef="92"', updated)
        self.assertIn('pageBreak="CELL"', updated)
        self.assertIn('repeatHeader="1"', updated)
        self.assertIn('noAdjust="1"', updated)

    def test_achievement_mov_stops_before_verification_location_and_judgment(self) -> None:
        item = (
            "성과지표: 자격시험 합격률\n"
            "기초선: 미기재\n목표치: 80%\n실적: 산출 대기\n달성률: 산출 유보\n"
            "검증수단: 자격시험 결과 보고서\n"
            "근거 위치: 5차년도 지표별 실적 현황, p.1\n"
            "판단: 진행 중"
        )
        fields = achievement_item_fields(item, 0)
        self.assertEqual(fields["mov"], "자격시험 결과 보고서")

    def test_achievement_layout_expands_every_indicator_group_from_content(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section5.xml").decode("utf-8")
        rows = "\n".join(
            f"| 성과 {index} | 지표 {index}의 충분한 설명 | 미기재 | {index}건 | "
            f"{index - 1}건 | {index * 10}% | 검증 보고서 {index} | 진행 중 |"
            for index in range(1, 15)
        )
        body = (
            "| 구분 | 성과지표 | 기초선 | 목표치 | 실적 | 달성률 | 검증수단 | 비고 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            + rows
        )
        populated = patch_hwpx_achievement_table_xml(xml, {"achievement": body})
        styled, changed = style_achievement_table_xml(populated)
        self.assertTrue(changed)
        tables = [
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:tbl")
            if all(
                token in get_hwpx_xml_scope_text(styled[start:end])
                for token in ("성과지표", "기초선", "달성도")
            )
        ]
        self.assertEqual(len(tables), len(ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS))
        self.assertEqual(len(tables), 3)
        self.assertGreaterEqual(
            len(re.findall(r'<hp:p\b[^>]*pageBreak="1"', styled)),
            len(ACHIEVEMENT_TABLE_PAGE_ITEM_GROUPS) - 1,
        )
        self.assertNotIn("…", get_hwpx_xml_scope_text(styled))
        from kodame_intake.hwpx_layout.tables import achievement_page_groups
        for table, item_group in zip(tables, achievement_page_groups(14)):
            self.assertIn('pageBreak="CELL"', table)
            self.assertIn('noAdjust="1"', table)
            rows = [table[start:end] for start, end in find_hwpx_tag_spans(table, "hp:tr")]
            self.assertEqual(
                len(rows),
                ACHIEVEMENT_HEADER_ROW_COUNT
                + len(item_group) * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
            )
            physical_heights = []
            for row_index, row in enumerate(rows):
                regular = []
                all_heights = []
                cells = [row[start:end] for start, end in find_hwpx_tag_spans(row, "hp:tc")]
                self.assertTrue(all(f'rowAddr="{row_index}"' in cell for cell in cells))
                if row_index >= ACHIEVEMENT_HEADER_ROW_COUNT:
                    self.assertTrue(all('vertAlign="TOP"' in cell for cell in cells))
                for cell in cells:
                    height = int(re.search(r'<hp:cellSz\b[^>]*height="(\d+)"', cell).group(1))
                    all_heights.append(height)
                    if 'rowSpan="1"' in cell:
                        regular.append(height)
                physical_heights.append(min(regular or all_heights))
            for group_start in range(
                ACHIEVEMENT_HEADER_ROW_COUNT,
                len(rows),
                ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
            ):
                group_rows = rows[group_start:group_start + 3]
                expected = achievement_item_group_height("".join(group_rows))
                self.assertGreaterEqual(expected, ACHIEVEMENT_GROUP_MIN_HEIGHT)
                self.assertEqual(sum(physical_heights[group_start:group_start + 3]), expected)
                self.assertEqual(
                    physical_heights[group_start:group_start + 3],
                    list(achievement_item_group_physical_heights(group_rows)),
                )
                self.assertNotIn('height="0"', "".join(rows[group_start:group_start + 3]))
            table_height = int(re.search(r'<hp:sz\b[^>]*height="(\d+)"', table).group(1))
            self.assertEqual(table_height, sum(physical_heights))

    def test_achievement_height_measures_long_text_in_second_and_third_physical_rows(self) -> None:
        def achievement_row(text: str, row_index: int) -> str:
            return (
                '<hp:tr><hp:tc><hp:subList>'
                '<hp:p><hp:run><hp:t>' + text + '</hp:t></hp:run></hp:p>'
                '</hp:subList>'
                f'<hp:cellAddr colAddr="0" rowAddr="{row_index}"/>'
                '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                '<hp:cellSz width="5200" height="1800"/>'
                '</hp:tc></hp:tr>'
            )

        rows = [
            achievement_row("짧은 값", 0),
            achievement_row("승인 여부와 국가 직무코드 제정 현황을 함께 확인하는 매우 긴 지표 값", 1),
            achievement_row("Master Instructor 인증 인원과 후속 갱신 여부를 함께 기록하는 긴 검증 값", 2),
        ]
        heights = achievement_item_group_physical_heights(rows)
        self.assertGreater(heights[1], heights[0])
        self.assertGreater(heights[2], heights[0])
        self.assertEqual(sum(heights), achievement_item_group_height("".join(rows)))

    def test_final_render_rejects_multiple_lines_with_collision_evidence(self) -> None:
        analysis = {
            "render": {
                "page_count": 47,
                "stats": {"table_count": 15},
                "line_overlap_risks": [
                    {
                        "page_number": 20,
                        "baseline_gap": 7.2,
                        "upper_text": "승인 여부 (유/무)",
                        "lower_text": "응급구조사",
                    }
                ],
            }
        }
        with self.assertRaisesRegex(RuntimeError, "여러 줄 글자 겹침 위험"):
            validate_render_result(analysis)

        analysis["render"]["line_overlap_risks"] = []
        self.assertEqual(validate_render_result(analysis), (47, 15))

    def test_numbered_criteria_after_first_always_start_on_new_page(self) -> None:
        source = "<hs:sec>" + "".join(
            paragraph(label, para_pr="15", char_pr="76")
            + paragraph(f"{label}의 충분한 본문", para_pr="71", char_pr="92")
            for label in (
                "1. 적절성",
                "2. 일관성",
                "3. 효과성",
                "4. 효율성",
                "5. 지속가능성",
                "6. 범분야 이슈",
                "7. 그 외 평가기준",
            )
        ) + "</hs:sec>"
        updated, changed = force_numbered_criterion_page_breaks_xml(source)
        self.assertEqual(changed, 5)
        first = next(
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:p")
            if get_hwpx_xml_scope_text(updated[start:end]).strip() == "1. 적절성"
        )
        self.assertNotIn('pageBreak="1"', first)
        for label in ("2. 일관성", "3. 효과성", "5. 지속가능성", "6. 범분야 이슈", "7. 그 외 평가기준"):
            self.assertTrue(heading_starts_on_fresh_page_xml(updated, label), label)
        self.assertFalse(heading_starts_on_fresh_page_xml(updated, "4. 효율성"))

    def test_grade_table_uses_project_name_only_and_readable_split_styles(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section2.xml").decode("utf-8")
        context = {
            "project": {"title": "테스트 사업명", "period": "2022~2029", "budget": "100억원"},
            "criteria": [],
            "overall": {},
        }
        patched = patch_hwpx_grade_section_xml(xml, context)
        self.assertIn("ㅇ 평가대상 사업명 : 테스트 사업명", patched)
        self.assertNotIn("2022~2029", patched)
        self.assertNotIn("100억원", patched)
        styled, changed = style_grade_table_xml(patched)
        self.assertTrue(changed)
        grade_tables = [
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:tbl")
            if "평가 기준" in get_hwpx_xml_scope_text(styled[start:end])
            and "핵심 질문" in get_hwpx_xml_scope_text(styled[start:end])
        ]
        self.assertEqual(len(grade_tables), len(GRADE_TABLE_PAGE_ROW_GROUPS))
        self.assertEqual(len(grade_tables), 2)
        self.assertGreaterEqual(
            len(re.findall(r'<hp:p\b[^>]*pageBreak="1"', styled)),
            len(GRADE_TABLE_PAGE_ROW_GROUPS) - 1,
        )
        question_count = subtotal_count = summary_count = 0
        expected_margin = (
            f'<hp:inMargin left="{GRADE_CELL_MARGIN_HORIZONTAL}" '
            f'right="{GRADE_CELL_MARGIN_HORIZONTAL}" '
            f'top="{GRADE_CELL_MARGIN_VERTICAL}" bottom="{GRADE_CELL_MARGIN_VERTICAL}"/>'
        )
        self.assertEqual(GRADE_CELL_MARGIN_VERTICAL, 100)
        for grade_table in grade_tables:
            self.assertIn('pageBreak="CELL"', grade_table)
            self.assertIn('repeatHeader="1"', grade_table)
            self.assertIn('noAdjust="1"', grade_table)
            self.assertIn('charPrIDRef="92"', grade_table)
            self.assertIn(expected_margin, grade_table)
            rows = find_hwpx_tag_spans(grade_table, "hp:tr")
            expected_table_height = 0
            for row_index, (row_start, row_end) in enumerate(rows):
                row = grade_table[row_start:row_end]
                row_text = get_hwpx_xml_scope_text(row)
                cells = [row[start:end] for start, end in find_hwpx_tag_spans(row, "hp:tc")]
                self.assertTrue(all(f'rowAddr="{row_index}"' in cell for cell in cells))
                heights = []
                for cell in cells:
                    if 'rowSpan="1"' not in cell:
                        continue
                    match = re.search(r'<hp:cellSz\b[^>]*height="(\d+)"', cell)
                    if match:
                        heights.append(int(match.group(1)))
                self.assertTrue(heights)
                row_height = min(heights)
                expected_table_height += row_height
                if row_index == 0:
                    self.assertEqual(row_height, GRADE_HEADER_ROW_HEIGHT)
                elif "평점(" in row_text:
                    subtotal_count += 1
                    self.assertEqual(row_height, GRADE_SUBTOTAL_ROW_HEIGHT)
                    reason_cell = next((cell for cell in cells if 'colAddr="4"' in cell), "")
                    self.assertEqual(get_hwpx_xml_scope_text(reason_cell).strip(), "")
                elif any(label in row_text for label in ("종합 점수", "종합 평가 등급", "KOICA 평가등급")):
                    summary_count += 1
                    self.assertEqual(row_height, GRADE_SUMMARY_ROW_HEIGHT)
                else:
                    question_count += 1
                    self.assertEqual(row_height, grade_question_row_height(row))
                    self.assertGreaterEqual(row_height, GRADE_QUESTION_MIN_HEIGHT)
                    self.assertLessEqual(row_height, GRADE_QUESTION_MAX_HEIGHT)
                    question_cell = next(cell for cell in cells if 'colAddr="1"' in cell)
                    reason_cell = next(cell for cell in cells if 'colAddr="4"' in cell)
                    self.assertIn("<hp:lineBreak/>", question_cell)
                    self.assertIn('paraPrIDRef="39"', question_cell)
                    self.assertTrue(get_hwpx_xml_scope_text(question_cell).strip().startswith("·"))
                    self.assertTrue(get_hwpx_xml_scope_text(reason_cell).strip())
                    self.assertIn('paraPrIDRef="39"', reason_cell)
                    self.assertNotIn("<hp:tab", reason_cell)
            table_size = re.search(r'<hp:sz\b[^>]*height="(\d+)"', grade_table)
            self.assertIsNotNone(table_size)
            self.assertEqual(int(table_size.group(1)), expected_table_height)
        self.assertEqual((question_count, subtotal_count, summary_count), (11, 5, 3))

    def test_grade_question_reason_removes_tabs_and_control_whitespace(self) -> None:
        reason = grade_question_reason("\t  근거 문서에서 성과가 확인됨\\t다만 후속 검증은 제한됨.\n", 120)
        self.assertNotIn("\t", reason)
        self.assertNotIn("\\t", reason)
        self.assertEqual(reason, "근거 문서에서 성과가 확인됨 다만 후속 검증은 제한됨.")

    def test_grade_manifest_cannot_restore_period_or_budget_to_project_label(self) -> None:
        context = {
            "project": {
                "title": "테스트 사업명",
                "period": "2022~2029",
                "budget": "100억원",
            },
            "criteria": {},
            "overall": {},
        }
        values = review_values_for_section(4, context, {})
        self.assertEqual(values["project_label"], "ㅇ 평가대상 사업명 : 테스트 사업명")
        self.assertNotIn("2022~2029", values["project_label"])
        self.assertNotIn("100억원", values["project_label"])

    def test_grade_manifest_applies_question_reasons_but_blanks_subtotal_reasons(self) -> None:
        context = {"project": {"title": "테스트 사업명"}, "criteria": {}, "overall": {}}
        section = structured_slots_to_json(
            "grade",
            {
                "relevance_policy_reason": "\t정책 부합 근거가 확인됨\\t다만 수요조사 범위는 제한됨.",
                "relevance_total_reason": "적절성 종합 평가 문구는 적용되면 안 됨",
            },
        )
        values = review_values_for_section(4, context, {"grade": section})
        self.assertEqual(values["relevance_policy_reason"], "정책 부합 근거가 확인됨 다만 수요조사 범위는 제한됨.")
        self.assertEqual(values["relevance_total_reason"], "")

        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section2.xml").decode("utf-8")
        applied, _ = patch_hwpx_review_section_slots_xml(xml, 4, context, {"grade": section})
        grade_table = next(
            applied[start:end]
            for start, end in find_hwpx_tag_spans(applied, "hp:tbl")
            if "종합 평가 등급" in applied[start:end]
        )
        cells = find_hwpx_tag_spans(grade_table, "hp:tc")
        self.assertEqual(get_hwpx_xml_scope_text(grade_table[cells[8][0]:cells[8][1]]).strip(), values["relevance_policy_reason"])
        for cell_index in GRADE_SUBTOTAL_REASON_CELLS:
            self.assertEqual(get_hwpx_xml_scope_text(grade_table[cells[cell_index][0]:cells[cell_index][1]]).strip(), "")

    def test_prepare_hwpx_sections_preserves_grade_slot_keys(self) -> None:
        section = structured_slots_to_json(
            "grade",
            {"relevance_policy_reason": "정책 수요와 사전타당성 근거를 교차 확인하여 4점을 적용함."},
        )
        prepared = preserve_structured_grade_section(section, "fallback")
        parsed = json.loads(prepared)
        self.assertIn("relevance_policy_reason", parsed["slots"])
        self.assertNotIn("relevance policy reason", parsed["slots"])

    def test_manual_grade_editor_save_preserves_machine_keys(self) -> None:
        section = structured_slots_to_json(
            "grade",
            {"relevance_policy_reason": "정책·수요 근거를 교차 확인하여 4점을 적용함."},
        )
        saved = sanitize_editor_part_response(section, "grade")
        parsed = json.loads(saved)
        self.assertEqual(
            parsed["slots"]["relevance_policy_reason"],
            "정책·수요 근거를 교차 확인하여 4점을 적용함.",
        )
        self.assertNotIn("relevance policy reason", parsed["slots"])

    def test_legacy_space_separated_grade_keys_are_repaired(self) -> None:
        legacy = json.dumps(
            {
                "schema": "section4 grade slots v1",
                "slots": {
                    "relevance policy reason": "현지 수요와 정책 근거를 확인하여 4점을 적용함.",
                    "relevance total reason": "삭제 대상",
                },
            },
            ensure_ascii=False,
        )
        repaired = json.loads(preserve_structured_grade_section(legacy, "fallback"))
        self.assertEqual(
            repaired["slots"]["relevance_policy_reason"],
            "현지 수요와 정책 근거를 확인하여 4점을 적용함.",
        )

    def test_grade_reason_is_concrete_without_generic_label_or_page_note(self) -> None:
        result = grade_question_reason(
            "본 사업은 교육과정 5종을 개설했으나 졸업생 취업 추적 근거는 부족하다 "
            "(1차년도 사업계획서, p. 7)."
        )
        self.assertNotIn("핵심 확인사항", result)
        self.assertNotIn("본 사업은", result)
        self.assertNotIn("p. 7", result)
        self.assertIn("교육과정 5종", result)

    def test_rendered_evaluation_matrix_heading_maps_to_its_page(self) -> None:
        page_map = toc_page_map_from_page_texts([
            (3, "1. 국문 요약"),
            (4, "II. 대상사업 개요\n1. 사업 추진배경\n2. 사업개요\n3. 사업설계매트릭스(PDM)"),
            (5, "1. 평가의 목적과 범위\n2. 평가매트릭스(Evaluation Matrix)\n3. 평가 방법"),
        ])
        self.assertEqual(page_map.get("evaluation_matrix_page"), "5")

    def test_evaluation_matrix_starts_with_spacing_and_splits_into_readable_pages(self) -> None:
        widths = (4751, 27674, 5034, 5317, 5266)
        header = ("평가기준", "평가질문", "측정지표", "자료출처", "분석방법")

        def cell(text: str, row: int, col: int, height: int = 1800) -> str:
            return (
                '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" '
                'dirty="0" borderFillIDRef="18">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="SQUEEZE" '
                'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
                'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                + paragraph(text, para_pr="49" if col == 0 else "39", char_pr="65" if row == 0 else "92")
                + "</hp:subList>"
                + f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
                '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                + f'<hp:cellSz width="{widths[col]}" height="{height}"/>'
                '<hp:cellMargin left="0" right="0" top="0" bottom="0"/>'
                "</hp:tc>"
            )

        rows = [
            "<hp:tr>" + "".join(cell(value, 0, col) for col, value in enumerate(header)) + "</hp:tr>"
        ]
        names = ("적절성", "일관성", "효과성", "효율성", "지속가능성", "인권", "성주류화", "환경")
        for row, name in enumerate(names, start=1):
            values = (
                f"{row}.{name}",
                "사업의 설계와 수행이 이해관계자의 수요와 우선순위를 반영하였는지 확인하는 핵심 평가질문임.",
                "목표 대비 실적과 참여 현황 및 제도화 수준",
                "사업계획서, PDM, 연차보고서와 공식 성과자료",
                "문헌검토, 자료 간 교차대조 및 기준별 판단",
            )
            rows.append(
                "<hp:tr>" + "".join(cell(value, row, col) for col, value in enumerate(values)) + "</hp:tr>"
            )
        table = (
            '<hp:tbl id="1330517739" pageBreak="TABLE" repeatHeader="1" '
            'rowCnt="9" colCnt="5" noAdjust="0">'
            '<hp:sz width="48042" height="16200"/>'
            '<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
            + "".join(rows)
            + "</hp:tbl>"
        )
        source = (
            "<hs:sec>"
            + paragraph("2. 평가매트릭스(Evaluation Matrix)", para_pr="15", char_pr="76")
            + '<hp:p id="1" paraPrIDRef="15" styleIDRef="0" pageBreak="0">'
            '<hp:run charPrIDRef="62"><hp:t>&lt;평가 매트릭스&gt;</hp:t>'
            + table
            + "</hp:run></hp:p></hs:sec>"
        )
        source, spaced = style_evaluation_matrix_heading_spacing_xml(source)
        styled, changed = style_evaluation_matrix_table_xml(source)
        self.assertTrue(spaced)
        self.assertTrue(changed)
        heading = next(
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:p")
            if "2. 평가매트릭스" in get_hwpx_xml_scope_text(styled[start:end])
            and "<hp:tbl" not in styled[start:end]
        )
        self.assertRegex(heading, r'paraPrIDRef="31"[^>]*pageBreak="1"')

        matrix_tables = [
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:tbl")
            if "평가질문" in get_hwpx_xml_scope_text(styled[start:end])
        ]
        self.assertEqual(len(matrix_tables), len(EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS))
        for matrix_table, row_group in zip(matrix_tables, EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS):
            self.assertTrue(all(
                token in matrix_table
                for token in ('pageBreak="CELL"', 'repeatHeader="1"', 'noAdjust="1"')
            ))
            self.assertIn(
                f'<hp:inMargin left="{EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL}" '
                f'right="{EVALUATION_MATRIX_CELL_MARGIN_HORIZONTAL}" '
                f'top="{EVALUATION_MATRIX_CELL_MARGIN_VERTICAL}" '
                f'bottom="{EVALUATION_MATRIX_CELL_MARGIN_VERTICAL}"/>',
                matrix_table,
            )
            matrix_rows = find_hwpx_tag_spans(matrix_table, "hp:tr")
            self.assertEqual(len(matrix_rows), len(row_group))
            for row_index, (start, end) in enumerate(matrix_rows):
                row_xml = matrix_table[start:end]
                expected_height = evaluation_matrix_row_height(row_xml, row_index)
                self.assertTrue(all(
                    int(value) == expected_height
                    for value in re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row_xml)
                ))

        shortened = styled.replace(
            "사업의 설계와 수행이 이해관계자의 수요와 우선순위를 반영하였는지 확인하는 핵심 평가질문임.",
            "핵심 평가질문임.",
        )
        refreshed_xml, refreshed_count = refresh_evaluation_matrix_split_heights_xml(shortened)
        self.assertEqual(refreshed_count, len(EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS))
        refreshed_tables = [
            refreshed_xml[start:end]
            for start, end in find_hwpx_tag_spans(refreshed_xml, "hp:tbl")
            if "평가질문" in get_hwpx_xml_scope_text(refreshed_xml[start:end])
        ]
        for matrix_table in refreshed_tables:
            matrix_rows = find_hwpx_tag_spans(matrix_table, "hp:tr")
            expected_total = 0
            for row_index, (start, end) in enumerate(matrix_rows):
                row_xml = matrix_table[start:end]
                expected_height = evaluation_matrix_row_height(row_xml, row_index)
                expected_total += expected_height
                self.assertTrue(all(
                    int(value) == expected_height
                    for value in re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row_xml)
                ))
            table_height = int(re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', matrix_table).group(1))
            self.assertEqual(table_height, expected_total)

    def test_achievement_report_rows_remain_grouped(self) -> None:
        raw = (
            "성과 달성도 분석\n"
            "ㅇ 구분: 필수\n"
            "- 성과목표 및 지표 (OVI): 교과목 수\n"
            "- 기초선 (Baselines): 0건\n"
            "- 목표치 (Targets): 5건\n"
            "- 누적달성치 / 실적: 4건\n"
            "- 달성률 (%): 80%\n"
            "- 검증수단 (MOV): 강의계획서\n"
            "- 달성 여부 및 미달성 원인 / 비고: 원고 보완 중\n"
            "ㅇ 구분: 자율\n"
            "- 성과목표 및 지표 (OVI): 교육 횟수\n"
            "- 기초선 (Baselines): 0회\n"
            "- 목표치 (Targets): 4회\n"
            "- 누적달성치 / 실적: 6회\n"
            "- 달성률 (%): 150%\n"
            "- 검증수단 (MOV): 결과보고서"
        )
        rows = parse_achievement_items(raw)
        self.assertEqual(len(rows), 2)
        self.assertIn("교과목 수", rows[0])
        self.assertIn("교육 횟수", rows[1])

    def test_achievement_narrative_after_table_is_not_parsed_as_a_pdm_row(self) -> None:
        raw = (
            "ㅇ 성과지표: 현지 교원 단독 운영 교과목 비율(%)\n"
            "- 기초선: 0%\n"
            "- 목표치: 100%\n"
            "- 실적: 60%\n"
            "- 달성률: 60%\n"
            "- 검증수단: 학사 운영 보고서\n"
            "ㅇ (차이 원인과 함의)\n"
            "- 성과지표의 후속 갱신 주기와 자료 책임자를 명확히 할 필요가 있다."
        )
        rows = parse_achievement_items(raw)
        self.assertEqual(len(rows), 1)
        self.assertIn("현지 교원 단독 운영", rows[0])

    def test_achievement_pdm_labels_expand_table_without_dropping_rows(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section5.xml").decode("utf-8")
        raw = "\n".join(
            "\n".join([
                f"ㅇ 계층: {'Outcome' if index <= 5 else 'Outputs'}",
                f"- PDM 지표명: 검증 지표 {index}",
                f"- 기초선: {index - 1}건",
                f"- 누적 목표치: {index + 5}건",
                f"- 누적 실적: {index + 4}건",
                f"- 달성률(%): {80 + index}%",
                f"- 검증수단(MOV): 검증자료 {index}",
                f"- 달성 여부 및 차이 원인 / 해설: 지표 {index} 해설",
            ])
            for index in range(1, 13)
        )

        updated = patch_hwpx_achievement_table_xml(xml, {"achievement": raw})
        table = next(
            updated[start:end]
            for start, end in find_hwpx_tag_spans(updated, "hp:tbl")
            if "성과지표" in updated[start:end] and "기초선" in updated[start:end] and "달성도" in updated[start:end]
        )
        cells = [
            get_hwpx_xml_scope_text(table[start:end]).strip()
            for start, end in find_hwpx_tag_spans(table, "hp:tc")
        ]

        self.assertIn('rowCnt="39"', table)
        self.assertEqual(len(cells), 188)
        for index in range(12):
            base = 20 + index * 14
            self.assertEqual(cells[base + 1], f"검증 지표 {index + 1}")
            self.assertEqual(cells[base + 2], f"{index}건")
            self.assertEqual(cells[base + 3], f"{index + 6}건")
            self.assertEqual(cells[base + 6], f"{index + 5}건")
            self.assertEqual(cells[base + 7], f"{81 + index}%")
            self.assertEqual(cells[base + 8], f"검증자료 {index + 1}")
        self.assertIsNone(re.search(r"기술능력증|학생 모집 저조", get_hwpx_xml_scope_text(table)))

    def test_achievement_adapter_accepts_llm_indicator_name_headers_after_normalization(self) -> None:
        source = (
            "| 지표 ID | 성과 지표 명칭 | 기초선 | 목표치 | 실적 (현재시점) | 검증수단 (MOV) | 달성 여부 및 원인 해설 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| outcome-1-1 | 현지 교원 단독 운영 교과목 비율(%) | 미기재 | 80% | 60% | 학사 운영 보고서 | 진행 중 |"
        )
        normalized, _ = normalize_section_text("achievement", source)
        rows = parse_achievement_items(normalized)
        fields = achievement_item_fields(rows[0], 0)

        self.assertEqual(fields["name"], "outcome-1-1")
        self.assertEqual(fields["indicator"], "현지 교원 단독 운영 교과목 비율(%)")
        self.assertEqual(fields["endline"], "60%")
        self.assertEqual(fields["mov"], "학사 운영 보고서")
        self.assertEqual(fields["note"], "진행 중")

    def test_background_plain_paragraphs_fill_five_distinct_slots(self) -> None:
        raw = "\n\n".join(f"사업배경 관점 {index}의 고유한 근거 문단이다." for index in range(1, 6))
        slots = _background_slots(raw)
        self.assertEqual(len(slots), 5)
        self.assertEqual(len(set(slots.values())), 5)
        for index, value in enumerate(slots.values(), start=1):
            self.assertIn(f"관점 {index}", value)
            self.assertRegex(value, r"^\([^()]+\) ")

    def test_project_background_markdown_headings_become_hanging_circle_paragraphs(self) -> None:
        normalized, _ = normalize_section_text(
            "project-background",
            "### 1. 개발문제와 응급의료 체계의 구조적 취약성\n\n현재 사업 근거를 서술한다.",
        )
        slots = _background_slots(normalized)
        first_value = slots["mdg_maternal_health_context"]
        self.assertTrue(first_value.startswith("(개발문제와 응급의료 체계의 구조적 취약성) "))
        source = (
            "<hs:sec>"
            + paragraph("1. 사업 추진배경", para_pr="15", char_pr="76")
            + paragraph(first_value)
            + paragraph("(정부 정책과 제도적 방향) 정책 근거를 서술한다.")
            + paragraph("(대상지역의 수요와 지원 필요성) 지역 근거를 서술한다.")
            + paragraph("(ODA 정책 및 지원전략과의 정합성) 정합성 근거를 서술한다.")
            + paragraph("(사업 선정과 형성 논리) 형성 논리를 서술한다.")
            + paragraph("2. 사업개요", para_pr="15", char_pr="76")
            + "</hs:sec>"
        )
        styled, changed = style_project_background_subheadings_xml(source)
        self.assertEqual(changed, 5)
        self.assertIn('<hp:t>ㅇ (개발문제와 응급의료 체계의 구조적 취약성)</hp:t>', styled)
        self.assertRegex(styled, r'paraPrIDRef="69"[^>]*>.*?charPrIDRef="18"')
        self.assertEqual(styled.count("<hp:lineBreak/>"), 5)
        self.assertRegex(
            styled,
            r'charPrIDRef="18"><hp:t>ㅇ \([^<]+\)</hp:t></hp:run>'
            r'<hp:run charPrIDRef="28"><hp:t><hp:lineBreak/>',
        )
        self.assertEqual(
            normalize_project_background_slot("government_policy_context", "ㅇ 기존 정책 근거를 서술한다."),
            "(정부 정책과 제도적 방향) 기존 정책 근거를 서술한다.",
        )

    def test_selected_headings_receive_exact_blank_line(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("앞 문단")
            + paragraph("4. 평가의 한계", para_pr="15", char_pr="76")
            + paragraph("한계 본문")
            + paragraph("5. 평가팀 구성 및 시행체계", para_pr="15", char_pr="76")
            + "</hs:sec>"
        )
        updated, changed = ensure_blank_line_before_headings_xml(
            source,
            {"4. 평가의 한계", "5. 평가팀 구성 및 시행체계"},
        )
        self.assertEqual(changed, 2)
        self.assertTrue(heading_has_blank_line_before_xml(updated, "4. 평가의 한계"))
        self.assertTrue(heading_has_blank_line_before_xml(updated, "5. 평가팀 구성 및 시행체계"))

    def test_all_in_flow_report_heading_roles_receive_one_blank_line(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph("앞선 결론 본문")
            + paragraph("2. 작동요인 및 비작동요인", para_pr="15", char_pr="76")
            + paragraph("")
            + paragraph("(1) 작동요인", para_pr="15", char_pr="76")
            + paragraph("하위 본문")
            + paragraph(" ㅇ 핵심 분석", para_pr="69", char_pr="28")
            + paragraph("추가 분석 본문")
            + paragraph("3. 종합 평가 및 시사점", para_pr="67", char_pr="18")
            + paragraph("새 쪽 제목", para_pr="15", char_pr="76").replace(
                'styleIDRef="0">', 'styleIDRef="0" pageBreak="1">'
            )
            + "</hs:sec>"
        )
        updated, changed = ensure_blank_line_before_report_headings_xml(source)
        self.assertEqual(changed, 3)
        self.assertTrue(
            heading_has_blank_line_before_xml(updated, "2. 작동요인 및 비작동요인")
        )
        self.assertTrue(heading_has_blank_line_before_xml(updated, "ㅇ 핵심 분석"))
        self.assertTrue(
            heading_has_blank_line_before_xml(updated, "3. 종합 평가 및 시사점")
        )
        self.assertEqual(report_heading_gap_violations_xml(updated), [])
        self.assertFalse(heading_has_blank_line_before_xml(updated, "새 쪽 제목"))

    def test_evaluation_overview_starts_on_fresh_page_after_one_page_pdm(self) -> None:
        source = (
            "<hs:sec>"
            + paragraph(EVALUATION_OVERVIEW_CHAPTER_HEADING, para_pr="15", char_pr="76")
            + paragraph("1. 평가의 목적과 범위")
            + "</hs:sec>"
        )
        updated, changed = ensure_page_break_before_heading_xml(
            source,
            EVALUATION_OVERVIEW_CHAPTER_HEADING,
        )
        self.assertTrue(changed)
        self.assertTrue(
            spacing_heading_starts_on_fresh_page_xml(
                updated,
                EVALUATION_OVERVIEW_CHAPTER_HEADING,
            )
        )

    def test_nonwhite_template_text_styles_become_black(self) -> None:
        header = (
            '<hh:charPr id="1" height="1100" textColor="#282828">x</hh:charPr>'
            '<hh:charPr id="2" height="1100" textColor="#0059FF">x</hh:charPr>'
            '<hh:charPr id="3" height="1100" textColor="#FFFFFF">x</hh:charPr>'
        )
        updated, changed = normalize_report_text_colors_header_xml(header)
        self.assertEqual(changed, 2)
        self.assertEqual(updated.count('textColor="#000000"'), 2)
        self.assertIn('textColor="#FFFFFF"', updated)

    def test_evaluation_overview_uses_exact_two_level_marker_spacing(self) -> None:
        normalized, _ = normalize_section_text(
            "eval-methods",
            "### 1. 평가 방법론 개요 및 기본 원칙\n본 평가는 증빙을 교차검증하였다.\n#### 1.1 문헌검토\n확정 문서를 검토하였다.",
        )
        self.assertEqual(
            normalized.splitlines(),
            [
                " ㅇ 평가 방법론 개요 및 기본 원칙",
                "  - 본 평가는 증빙을 교차검증하였음.",
                "  - 문헌검토 확정 문서를 검토하였음.",
            ],
        )
        self.assertEqual(hwpx_report_body_lines(normalized), normalized.splitlines())

    def test_numbered_lessons_keep_all_items(self) -> None:
        raw = "## VI. 결론\n\n### 3. 환류과제 및 교훈\n\n#### (2) 교훈 (Lessons)\n\n" + "\n".join(
            f"##### 교훈 {index}. (원칙 {index})\n- 교훈 내용: 일반화 내용 {index}\n- 분야/일반 구분: 일반\n- 이전년도 교훈 중복 여부: 신규\n- 체크리스트 질문: 점검 질문 {index}?"
            for index in range(1, 6)
        )
        rows = parse_lesson_items(raw)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["lesson"], "일반화 내용 1")
        self.assertEqual(rows[-1]["checklist"], "점검 질문 5?")

    def test_four_lessons_share_one_height_safe_table_page(self) -> None:
        root = Path(__file__).resolve().parents[3]
        template = root / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
        with zipfile.ZipFile(template, "r") as archive:
            xml = archive.read("Contents/section8.xml").decode("utf-8")
        lessons = "\n".join(
            (
                f"##### 교훈 {index}. (원칙 {index})\n"
                f"- 교훈 내용: 유사 사업 설계와 수행에서 원칙 {index}을 점검해야 함.\n"
                "- 분야/일반 구분: 일반\n"
                "- 이전년도 교훈 중복 여부: 신규\n"
                f"- 체크리스트 질문: 원칙 {index}의 이행 근거가 축적되고 있는가?"
            )
            for index in range(1, 5)
        )
        populated = patch_hwpx_feedback_lessons_tables_xml(xml, {"lessons": lessons})
        styled, checks = style_recommendation_tables_xml(populated)
        tables = [
            styled[start:end]
            for start, end in find_hwpx_tag_spans(styled, "hp:tbl")
            if "평가 교훈 분석" in get_hwpx_xml_scope_text(styled[start:end])
            and "체크리스트" in get_hwpx_xml_scope_text(styled[start:end])
        ]
        self.assertEqual(LESSONS_ROWS_PER_PAGE, 4)
        self.assertEqual(checks["lessons_table_pages"], 1)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(find_hwpx_tag_spans(tables[0], "hp:tr")), 6)
        table_text = get_hwpx_xml_scope_text(tables[0])
        self.assertTrue(
            all(
                f"유사 사업 설계와 수행에서 원칙 {index}을 점검해야 함" in table_text
                for index in range(1, 5)
            ),
            table_text,
        )
        table_height = int(re.search(r'<hp:sz\b[^>]*\bheight="(\d+)"', tables[0]).group(1))
        self.assertLessEqual(table_height, LESSONS_MAX_TABLE_HEIGHT)

    def test_theory_drops_parent_headings_and_normalizes_double_numbering(self) -> None:
        raw = (
            "## VI. 결론\n\n"
            "### 2. 작동요인 및 비작동요인\n\n"
            "#### (3) 변화이론 분석\n\n"
            "#### ① 투입 및 활동 경로\n본문 1\n\n"
            "#### ② 산출 및 성과 경로\n본문 2"
        )
        normalized, _ = normalize_section_text("theory", raw)
        self.assertNotIn("정규 응급구조학과", normalized)
        self.assertNotIn("VI. 결론", normalized)
        self.assertNotIn("작동요인 및 비작동요인", normalized)
        self.assertIn("  - 투입 및 활동 경로", normalized)
        self.assertIn("  - 산출 및 성과 경로", normalized)


if __name__ == "__main__":
    unittest.main()
