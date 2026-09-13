from __future__ import annotations

import unittest

from kodame_intake.report_sources import (
    is_report_evidence_document,
    normalize_source_mentions,
    reader_source_label,
    source_artifact_issues,
    strip_inline_source_citations,
)


class ReportSourcePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_name = "사업기본자료_DAC_PDM_2026-08-27_최신_PDM_국립한국교통대학교.pdf"

    def test_reader_label_removes_upload_management_artifacts(self) -> None:
        label = reader_source_label(self.raw_name)

        self.assertIn("사업설계매트릭스(PDM)", label)
        for forbidden in ("사업기본자료", "DAC_PDM", "2026-08-27", ".pdf", "_", "한국교통대학교"):
            self.assertNotIn(forbidden, label)

    def test_normalizer_replaces_exact_raw_filename_and_html_breaks(self) -> None:
        source = f"근거: {self.raw_name}<br>성과를 확인하였다."
        normalized = normalize_source_mentions(source, [self.raw_name])

        self.assertIn("사업설계매트릭스(PDM)", normalized)
        self.assertIn("\n", normalized)
        self.assertEqual(source_artifact_issues(normalized, [self.raw_name]), [])

    def test_operational_upload_artifacts_are_not_report_evidence(self) -> None:
        for name in (
            "README.md",
            "업로드_안내.txt",
            "자료요청_메일초안.md",
            "Google_Drive_생성_공유_절차.txt",
            "자료없음_확인서.txt",
        ):
            self.assertFalse(is_report_evidence_document(name))
        self.assertTrue(is_report_evidence_document("성과지표_실적증빙.xlsx"))

    def test_validator_reports_raw_identifiers(self) -> None:
        issues = source_artifact_issues(f"{self.raw_name}을 확인함", [self.raw_name])
        self.assertTrue(any("원본 업로드 파일명" in item for item in issues))
        self.assertTrue(any("원본 파일 확장자" in item for item in issues))
        self.assertEqual(source_artifact_issues("정상적인_내부 식별자"), [])

    def test_validator_reports_internal_paths_and_upload_dates_near_source_labels(self) -> None:
        label = reader_source_label(self.raw_name)
        issues = source_artifact_issues(
            f"내부 위치 /app/uploads/report.pdf 및 {label} 2026-08-27을 확인함",
            [self.raw_name],
        )

        self.assertTrue(any("내부 저장 경로" in item for item in issues))
        self.assertTrue(any("업로드일 관리정보" in item for item in issues))
        self.assertEqual(
            source_artifact_issues("평가 기준일은 2026-08-27이다.", [self.raw_name]),
            [],
        )
        self.assertEqual(
            source_artifact_issues("공개 근거 URL은 https://example.org/report이다.", [self.raw_name]),
            [],
        )

    def test_inline_source_locations_are_removed_but_normal_parentheses_remain(self) -> None:
        source = (
            "사업은 현지 역량을 강화하였다 (4차년도 자체평가결과보고서, pp.18-20). "
            "최신 지표도 확인하였다 (최신 사업설계매트릭스(PDM), p. 7). "
            "진행 상태도 검토하였다 (4차년도 자체평가결과보고서).\n"
            "- 근거 위치: 5차년도 지표별 실적 현황, p.1\n"
            "수행기관(ASMI)의 역할은 유지한다."
        )
        cleaned = strip_inline_source_citations(source)
        self.assertEqual(
            cleaned,
            "사업은 현지 역량을 강화하였다. 최신 지표도 확인하였다. 진행 상태도 검토하였다.\n수행기관(ASMI)의 역할은 유지한다.",
        )
        self.assertNotIn("pp.18-20", cleaned)
        self.assertNotIn("근거 위치", cleaned)
        self.assertIn("(ASMI)", cleaned)


if __name__ == "__main__":
    unittest.main()
