import unittest

from backend.oda_me.reports.overview_records import legacy_overview_slots
from backend.oda_me.hwpx.patchers import parse_feedback_items
from kodame_intake.hwpx_pipeline import _overview_slots


class OverviewFeedbackMappingTests(unittest.TestCase):
    def test_flat_legacy_values_preserved_in_twelve_cells(self):
        parts = [
            "▣ 국문: A/B 사업", "▣ 영문: Original English Title", "▣ 국가/지역",
            "▣ 구분: 사업", "▣ 기간: 2022/04~2029/03", "▣ 총 사업예산: 27.7억",
            "▣ 프로젝트 / 보건·의료", "▣ 목적1", "▣ 목적2",
            "󰁯 관계기관 PCP: 미기재", "󰁯 사전타당성조사: 실시",
        ]
        for i in range(4):
            parts.extend([f"▣ 소요예산: {i}.5억", f"▪ 지원내용{i}"])
        parts.append("▣ 협력기관 공간/인력 지원")
        raw = " / ".join(parts)
        slots = _overview_slots({}, raw, raw)
        self.assertEqual(len(slots), 12)
        self.assertEqual(slots["project_name_en"], parts[1])
        self.assertEqual(slots["project_sector"], "▣ 프로젝트 / 보건·의료")
        self.assertEqual(slots["pcp_feasibility_review"], " / ".join(parts[9:11]))
        self.assertEqual(slots["korean_expert_dispatch"], "▣ 소요예산: 2.5억 / ▪ 지원내용2")
        self.assertEqual(" / ".join(slots.values()), raw)

    def test_ambiguous_legacy_fails_instead_of_filling_pcp_with_entire_text(self):
        self.assertIsNone(legacy_overview_slots("▣ 국문: 사업 / ▣ 알 수 없는 항목"))
        with self.assertRaises(ValueError):
            _overview_slots({}, "▣ 국문: 사업 / ▣ 알 수 없는 항목", "")

    def test_feedback_each_field_stops_before_next_label(self):
        text = """1. 구분: 사업관리 개선제언
- 제언: 지표 담당자를 지정함
- 이해관계자: 사업단
- 선정 사유: 정량적 추적 기반 필요함
- 우선순위: 상
- 완료기한: 2026-12-31
- 점검주기: 분기
- 후속 확인자료: 모니터링 대장"""
        rows = parse_feedback_items(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "우선순위: 상 | 선정 사유: 정량적 추적 기반 필요함")
        self.assertEqual(rows[0]["opinion"], "완료기한: 2026-12-31 | 점검주기: 분기 | 확인자료: 모니터링 대장")
        self.assertEqual(rows[0]["priority"], "상")
        self.assertEqual(rows[0]["due_date"], "2026-12-31")


if __name__ == "__main__":
    unittest.main()
