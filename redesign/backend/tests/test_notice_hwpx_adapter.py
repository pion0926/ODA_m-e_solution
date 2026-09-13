from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from kodame_intake.hwpx_adapters.sections.section03_notice import patch_xml
from kodame_intake.hwpx_adapters.section_adapter import SectionPatchResult

ROOT = Path(__file__).resolve().parents[3]


class NoticeAdapterTests(unittest.TestCase):
    def test_saved_body_is_preserved_in_template_without_changing_grade_table(self):
        from kodame_intake.report_section_preview import isolate_section_xml
        with ZipFile(ROOT / "samples/5-1. 종료평가 결과보고서 placeholder.hwpx") as archive:
            original = archive.read("Contents/section2.xml").decode("utf-8")
        body = " ㅇ 평가 범위\n- 현재 사업의 증빙을 기준으로 검토함.\n\n ㅇ 품질관리\n- 새로운 근거자료가 확보되면 관련 평가 판단과 보고서 내용을 함께 갱신함."
        result = patch_xml(original, {"project": {"title": "검증 사업"}}, {"notice": body})
        visible = "".join(ET.fromstring(result.xml).itertext())
        for line in body.splitlines():
            if line.strip():
                self.assertIn(line.strip(), visible)
        self.assertIn("평가 기준일", visible)
        self.assertIn("외부 품질심의", visible)
        self.assertEqual(isolate_section_xml(original, "grade"), isolate_section_xml(result.xml, "grade"))
        self.assertEqual(result.metrics["notice_body_lines"], 4)

    def test_missing_body_slot_fails_closed(self):
        with patch("kodame_intake.hwpx_adapters.sections.section03_notice.patch_review_section", return_value=SectionPatchResult("<p>다른 내용</p>", 0, {})):
            with self.assertRaisesRegex(ValueError, "저장된 본문"):
                patch_xml("", {}, {"notice": "수정 요청이 반영된 고유 본문임."})


if __name__ == "__main__":
    unittest.main()
