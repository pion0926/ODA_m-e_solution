from __future__ import annotations

import unittest
from datetime import date
from io import BytesIO
import zipfile

from kodame_intake.assessment_context import project_phase
from kodame_intake.document_slots import document_slot_matches
from kodame_intake.report_exporter import (
    _clean_toc_annotations_xml,
    _local_validate,
    _replace_stale_theory_pictures_xml,
    _scrub_xml_reader_text,
    _split_cover_title,
    _wrap_cover_title_xml,
)
from kodame_intake.report_generator import (
    _apply_reader_normalizations,
    _deterministic_quality_cap,
    _editor_revision_context,
    _ensure_official_grade_statement,
    _quality_prompt,
    _quantitative_consistency_issues,
    _validate_reader_content,
)
from kodame_intake.hwpx_layout.validation import _has_inline_source_citation


class QualityGuardTests(unittest.TestCase):
    def _minimal_hwpx(self, visible_text: str) -> bytes:
        output = BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("META-INF/container.xml", "<container/>")
            archive.writestr("Contents/content.hpf", "<package/>")
            archive.writestr("Contents/header.xml", "<header/>")
            archive.writestr("Contents/section0.xml", f"<hp:p><hp:run><hp:t>{visible_text}</hp:t></hp:run></hp:p>")
        return output.getvalue()

    def test_hwpx_validation_allows_deliberate_evidence_gap_text(self) -> None:
        result = _local_validate(self._minimal_hwpx("현지 조사 결과는 확인 필요"), {"title": "현재 사업"})
        self.assertTrue(result["zip_ok"])

    def test_hwpx_validation_still_rejects_real_template_placeholder(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "미치환 독자표시"):
            _local_validate(self._minimal_hwpx("평가책임자 OOO"), {"title": "현재 사업"})

    def test_reader_text_scrub_removes_markdown_authoring_markers(self) -> None:
        xml = '<hp:p><hp:run><hp:t>**달성**<hp:lineBreak/>__검토__</hp:t></hp:run></hp:p>'
        cleaned = _scrub_xml_reader_text(xml, {"title": "현재 사업"})
        self.assertIn("달성<hp:lineBreak/>검토", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("__", cleaned)

    def test_reader_text_scrub_preserves_toc_tab_leader(self) -> None:
        xml = (
            '<hp:p><hp:run><hp:t>1. 국문 요약'
            '<hp:tab width="33800" leader="3" type="2"/>'
            '</hp:t></hp:run><hp:run><hp:t>5</hp:t></hp:run></hp:p>'
        )
        cleaned = _scrub_xml_reader_text(xml, {"title": "현재 사업"})
        self.assertIn('<hp:tab width="33800" leader="3" type="2"/>', cleaned)
        self.assertIn("1. 국문 요약", cleaned)

    def test_reader_text_scrub_preserves_spaces_between_mixed_style_runs(self) -> None:
        xml = (
            '<hp:p><hp:run charPrIDRef="28"><hp:t xml:space="preserve">- </hp:t></hp:run>'
            '<hp:run charPrIDRef="18"><hp:t>(산출·성과 진척)</hp:t></hp:run>'
            '<hp:run charPrIDRef="28"><hp:t xml:space="preserve"> 본문을 종합함.</hp:t></hp:run></hp:p>'
        )
        cleaned = _scrub_xml_reader_text(xml, {"title": "현재 사업"})
        self.assertIn('xml:space="preserve">- </hp:t>', cleaned)
        self.assertIn('xml:space="preserve"> 본문을 종합함.</hp:t>', cleaned)
        self.assertFalse(_has_inline_source_citation(" - (산출·성과 진척) 본문을 종합함. "))
        self.assertFalse(_has_inline_source_citation("  -  (산출·성과 진척)  본문을 종합함 . "))
        self.assertTrue(_has_inline_source_citation("본문을 확인함 (자체평가보고서, p. 7)."))

    def test_report_visuals_keep_only_theory_frame(self) -> None:
        xml = (
            '<hp:p><hp:run><hp:t>(3) 변화이론 분석</hp:t></hp:run></hp:p>'
            '<hp:p pageBreak="0"><hp:run><hp:pic>'
            '<hp:offset x="17432" y="4294944366"/>'
            '<hp:orgSz width="144000" height="65160"/>'
            '<hp:curSz width="70330" height="31821"/>'
            '<hp:rotationInfo angle="0" centerX="35165" centerY="15910" rotateimage="1"/>'
            '<hp:renderingInfo><hc:transMatrix e1="1"/><hc:scaMatrix e1="0.4"/>'
            '<hc:rotMatrix e1="1"/></hp:renderingInfo>'
            '<hc:img binaryItemIDRef="image3"/>'
            '<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="144000" y="0"/>'
            '<hc:pt2 x="144000" y="65160"/><hc:pt3 x="0" y="65160"/></hp:imgRect>'
            '<hp:imgClip left="0" right="109140" top="0" bottom="49440"/>'
            '<hp:imgDim dimwidth="109140" dimheight="49440"/>'
            '<hp:pos treatAsChar="1" horzRelTo="PARA" horzAlign="LEFT"/>'
            '</hp:pic></hp:run></hp:p>'
            '<hp:p><hp:run><hp:pic><hc:img binaryItemIDRef="image2"/></hp:pic></hp:run></hp:p>'
            '<hp:p><hp:run><hp:pic><hc:img binaryItemIDRef="image1"/></hp:pic></hp:run></hp:p>'
            '<hp:p><hp:run><hp:t>3. 환류과제 및 교훈</hp:t></hp:run></hp:p>'
        )
        updated, kept, removed = _replace_stale_theory_pictures_xml(xml)
        self.assertEqual((kept, removed), (1, 2))
        self.assertEqual(updated.count("<hp:pic"), 1)
        self.assertEqual(updated.count('binaryItemIDRef="image1"'), 1)
        self.assertNotIn('binaryItemIDRef="image2"', updated)
        self.assertNotIn('binaryItemIDRef="image3"', updated)
        self.assertEqual(updated.count('pageBreak="1"'), 1)
        self.assertEqual(updated.count('pageBreak="0"'), 0)
        self.assertGreaterEqual(updated.count('<hp:imgClip left="0" right="160000" top="0" bottom="90000"/>'), 1)
        self.assertGreaterEqual(updated.count('<hp:imgDim dimwidth="160000" dimheight="90000"/>'), 1)
        self.assertIn('width="70400"', updated)
        self.assertIn('height="39600"', updated)
        self.assertIn('<hp:orgSz width="160000" height="90000"/>', updated)
        self.assertIn('<hp:curSz width="70400" height="39600"/>', updated)
        self.assertIn('<hc:pt2 x="160000" y="90000"/>', updated)
        self.assertIn('paraPrIDRef="4"', updated)
        self.assertIn('<hc:scaMatrix e1="0.44"', updated)
        self.assertIn('horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER"', updated)

    def test_project_period_month_is_valid_through_the_last_day(self) -> None:
        self.assertEqual(project_phase("2022.04–2026.08", date(2026, 8, 31)), "ongoing")
        self.assertEqual(project_phase("2022.04–2026.08", date(2026, 9, 1)), "ended")

    def test_slot_selection_uses_summary_signals_not_only_generic_file_name(self) -> None:
        matches = document_slot_matches("2025년 사업계획서.pdf", {
            "document_type": "연차 계획서",
            "dac_criteria": ["efficiency"],
            "summary": "기자재 입찰, 계약, 납품과 검수 일정을 상세히 정리한 조달 문서",
            "oda_categories": ["조달관리"],
        })
        self.assertEqual(matches[0]["slot_id"], "efficiency-procurement")
        self.assertGreater(matches[0]["confidence"], 0.7)

    def test_achievement_rate_mismatch_is_rejected(self) -> None:
        content = (
            "| 구분 | 지표 | 설명 | 기초선 | 목표 | 실적 | 달성률 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 필수 | 교육 | - | 0회 | 4회 | 6회 | 80% |"
        )
        issues = _quantitative_consistency_issues("achievement", content, [])
        self.assertTrue(any("산식 불일치" in issue for issue in issues))

    def test_korean_word_possible_does_not_trigger_ghana_reference_leak(self) -> None:
        content = "사업기간 내 성과 달성이 가능하며, 가능성은 후속 자료로 점검한다. " * 20
        issues = _validate_reader_content(
            "criteria-relevance",
            content,
            "우즈베키스탄",
            {"project_status": "ongoing", "commissioning_agency": "교육부"},
        )
        self.assertFalse(any("가나" in issue for issue in issues))

    def test_cover_title_wrap_and_toc_annotation_cleanup(self) -> None:
        title = "우즈베키스탄 안디잔주 의과대학 응급구조학과 신설 및 교육프로그램 구축 사업"
        xml = f'<hp:p><hp:run><hp:t>{title} </hp:t></hp:run></hp:p>'
        wrapped, count = _wrap_cover_title_xml(xml, {"title": title})
        self.assertEqual(count, 1)
        self.assertIn("<hp:lineBreak/>", wrapped)
        self.assertEqual(_clean_toc_annotations_xml("평가등급 결과표 (준비도) 교훈 (선택)"), "평가등급 결과표 교훈")
        self.assertEqual(
            _clean_toc_annotations_xml("1. 평가매트릭스(Evaluation Matrix)"),
            "2. 평가매트릭스(Evaluation Matrix)",
        )

    def test_cover_title_never_leaves_connector_on_its_own_line(self) -> None:
        title = "우즈베키스탄 응급구조학과 구축 및 지역사회 CPCR, MCI Triage 교육 프로그램"
        lines = _split_cover_title(title)
        self.assertNotIn("및", lines)
        self.assertFalse(any(line.startswith("및 ") or line.endswith(" 및") for line in lines))
        self.assertFalse(any(len(line.split()) == 1 for line in lines))
        self.assertLessEqual(max(map(len, lines)) - min(map(len, lines)), 8)

    def test_reader_minimum_is_a_hard_threshold(self) -> None:
        content = "현재 사업 근거를 분석한다. " * 20
        issues = _validate_reader_content(
            "criteria-other",
            content,
            "우즈베키스탄",
            {"project_status": "ongoing", "commissioning_agency": "교육부"},
        )
        self.assertTrue(any("목표 최소 분량 미달" in issue for issue in issues))

    def test_reader_normalization_applies_dac_acronym_and_tone_policy(self) -> None:
        source = (
            "DAC 6대 평가기준은 적절성, 일관성, 효과성, 효율성, 파급효과(Impact), 지속가능성이다. "
            "RAC 자료를 아카데빙하며 성과가 완벽하다."
        )
        normalized = _apply_reader_normalizations(
            "conclusion", source, {"official_acronyms": [{"acronym": "RRCEM"}]}
        )
        self.assertIn("DAC 5대", normalized)
        self.assertIn("적절성, 일관성, 효과성, 효율성, 지속가능성", normalized)
        self.assertIn("RRCEM", normalized)
        self.assertIn("기록·보관", normalized)
        for forbidden in ("파급효과(Impact)", "RAC", "아카데빙", "완벽"):
            self.assertNotIn(forbidden, normalized)

    def test_feedback_requires_operational_control_fields_per_item(self) -> None:
        content = "\n".join([
            "1. 구분: 성과관리\n- 제언: 조치 1\n- 우선순위: 상\n- 완료기한: 2026.12\n- 점검주기: 월\n- 후속 확인자료: 보고서",
            "2. 구분: 제도\n- 제언: 조치 2\n- 우선순위: 중\n- 완료기한: 2027.03\n- 점검주기: 분기\n- 후속 확인자료: 회의록",
            "3. 구분: 예산\n- 제언: 조치 3\n- 우선순위: 하\n- 점검주기: 반기\n- 후속 확인자료: 예산서",
        ])
        # Repeat only to satisfy the section length contract; the missing
        # field must still be detected against the three actual items.
        content += "\n" + ("선정 사유와 이행 경로를 구체화한다. " * 80)
        issues = _validate_reader_content(
            "feedback", content, "우즈베키스탄",
            {"project_status": "ongoing", "commissioning_agency": "교육부"},
        )
        self.assertTrue(any("완료기한 필드 누락" in issue for issue in issues))

    def test_grade_and_conclusion_require_official_twenty_point_grades(self) -> None:
        evaluations = [
            {"criterion_id": "relevance", "score": 3.5},
            {"criterion_id": "coherence", "score": 2.5},
            {"criterion_id": "effectiveness", "score": 2.7},
            {"criterion_id": "efficiency", "score": 3.0},
            {"criterion_id": "sustainability", "score": 3.0},
        ]
        issues = _quantitative_consistency_issues("grade", "종합등급은 우수/양호 수준이다.", evaluations)
        self.assertTrue(any("14.7/20점" in issue for issue in issues))
        self.assertTrue(any("공식 KOICA 등급" in issue for issue in issues))
        self.assertTrue(any("공식 국무조정실 등급" in issue for issue in issues))
        completed = _ensure_official_grade_statement("conclusion", "성과와 한계를 종합한다.", evaluations)
        self.assertIn("14.7/20점", completed)
        self.assertIn("KOICA 등급 C", completed)
        self.assertIn("국무조정실 등급 성공적", completed)
        reader_issues = _validate_reader_content(
            "conclusion",
            completed + "\n" + ("판단의 근거와 한계를 균형 있게 서술한다. " * 80),
            "우즈베키스탄",
            {"project_status": "ongoing", "commissioning_agency": "교육부"},
        )
        self.assertFalse(any("KOICA·코이카 정보" in issue for issue in reader_issues))

    def test_feedback_markdown_contract_is_accepted(self) -> None:
        content = (
            "| 구분 | 제언 | 이해관계자 | 선정 사유 | 우선순위 | 완료기한 | 점검주기 | 후속 확인자료 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            + "\n".join(
                f"| 성과관리 | 조치 {index} | 수행기관 | 근거 {index} | 상 | 2026-12-31 | 월간 | 보고서 {index} |"
                for index in range(1, 4)
            )
            + "\n" + ("각 과제의 실행 경로와 검증 방법을 설명한다. " * 100)
        )
        issues = _validate_reader_content(
            "feedback", content, "우즈베키스탄",
            {"project_status": "ongoing", "commissioning_agency": "교육부"},
        )
        self.assertFalse(any("환류과제" in issue for issue in issues))

    def test_quality_score_is_capped_when_inline_source_location_remains(self) -> None:
        content = ("참여자 29명이 교육 6회를 수료했다 (자체평가보고서, pp. 18-20). " * 80)
        cap, issues = _deterministic_quality_cap("criteria-effectiveness", content, {}, False)
        self.assertEqual(cap, 84.0)
        self.assertTrue(any("위치 인용이 남아 있음" in issue for issue in issues))

    def test_reader_text_scrub_removes_inline_page_citations_across_sections(self) -> None:
        xml = (
            '<hp:p><hp:run><hp:t>사업 성과를 확인하였다 '
            '(4차년도 자체평가결과보고서, pp.18-20).</hp:t></hp:run></hp:p>'
        )
        cleaned = _scrub_xml_reader_text(xml, {"title": "현재 사업"})
        self.assertIn("사업 성과를 확인하였다.", cleaned)
        self.assertNotIn("pp.18-20", cleaned)

    def test_editor_revision_context_contains_current_content_and_user_request(self) -> None:
        context = _editor_revision_context(
            "기존 본문에는 성과와 한계가 함께 정리되어 있다.",
            "결론을 문제 중심으로 바꾸고 한계는 유지해줘.",
        )
        self.assertIn("[수정 전 현재 섹션 본문]", context)
        self.assertIn("기존 본문에는 성과와 한계", context)
        self.assertIn("[사용자 수정 요청]", context)
        self.assertIn("결론을 문제 중심으로", context)
        self.assertIn("요청하지 않은 정확한 내용", context)

    def test_quality_prompt_rechecks_revision_request(self) -> None:
        section = {
            "part_id": "conclusion", "title": "결론", "prompt": "평가 결론을 작성한다.",
            "required_inputs": [],
        }
        prompt = _quality_prompt(
            section, [], [], {}, [], [], {}, "1차 수정 결과",
            "수정 전 내용", "핵심 제언을 세 문장으로 줄여줘.",
        )
        self.assertIn("수정 전 내용", prompt)
        self.assertIn("핵심 제언을 세 문장으로", prompt)
        self.assertIn("1차 작성·수정 결과", prompt)
        self.assertIn("실제로 반영했는지", prompt)


if __name__ == "__main__":
    unittest.main()
