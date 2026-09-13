from __future__ import annotations

import unittest
from unittest.mock import patch

from kodame_intake.pdm_monitoring import (
    _attach_performance_risk_analysis,
    _fallback_performance_risk,
    _monitoring_indicators_from_pdm,
)
from kodame_intake.openrouter import clean_risk_text
from kodame_intake.main import _clean_risk_payload


class PerformanceRiskAnalysisTests(unittest.TestCase):
    def test_monitoring_roster_contains_only_pdm_objective_indicators(self) -> None:
        tiers = [
            {
                "id": "impact", "name": "영향", "summary": "상위목표", "indicators": [
                    {"id": "impact-1", "code": "1", "text": "병원 전 단계 사망률 감소율(%)", "mov": "보건통계 연보"},
                ],
            },
            {
                "id": "outcome", "name": "성과", "summary": "성과목표", "indicators": [
                    {"id": "outcome-2-1", "code": "2-1", "text": "응급구조사 졸업시험 합격률(%)", "mov": "자격시험 결과"},
                    {"id": "outcome-2-2", "code": "2-2", "text": "졸업생의 전공 관련 분야 취업률(%)", "mov": "취업 현황"},
                ],
            },
            {
                "id": "outputs", "name": "산출물", "summary": "강사 양성", "indicators": [
                    {"id": "outputs-3-1", "code": "3.1-1", "text": "양성된 지역사회 CPCR 전문 강사(Instructor) 수 (명)", "mov": "강사 자격증 발급 대장"},
                ],
            },
        ]
        reported = [
            {"indicator": "자격시험 합격률(%)", "target": "0.8", "actual": "0.7", "achievement_rate": 87.5, "status": "watch"},
            {"indicator": "취업률", "target": "0.7", "actual": "-", "achievement_rate": None, "status": "unset"},
            {"indicator": "CPCR 강사 양성여부(명)", "target": "10명", "actual": "6명", "achievement_rate": 60.0, "status": "under"},
            {"indicator": "CPCR 강사 교육 및 자체 교육 횟수(회)", "target": "2회", "actual": "4회", "achievement_rate": 200.0, "status": "ok"},
            {"indicator": "위원회 회의 개최 횟수", "target": "2회", "actual": "1회", "achievement_rate": 50.0, "status": "under"},
        ]

        result = _monitoring_indicators_from_pdm(tiers, reported, [])

        self.assertEqual([item["id"] for item in result], ["impact-1", "outcome-2-1", "outcome-2-2", "outputs-3-1"])
        self.assertEqual(result[0]["tier_label"], "Impact(영향)")
        self.assertEqual(result[0]["status"], "unset")
        self.assertEqual(result[1]["tier_label"], "Outcome(성과)")
        self.assertEqual(result[1]["target"], "80%")
        self.assertEqual(result[1]["actual"], "70%")
        self.assertEqual(result[2]["reported_indicator"], "취업률")
        self.assertEqual(result[2]["target"], "70%")
        self.assertEqual(result[3]["reported_indicator"], "CPCR 강사 양성여부(명)")
        self.assertEqual(result[3]["target"], "10명")
        self.assertEqual(result[3]["actual"], "6명")
        self.assertNotIn("위원회 회의", " ".join(item["indicator"] for item in result))

    def test_risk_text_repairs_broken_korean_word_and_punctuation(self) -> None:
        self.assertEqual(clean_risk_text("현지 기관 협,공문을 확인한다."), "현지 기관 협의 공문을 확인한다.")
        payload = {"evidence_needed": ["추가 조사계획서", "현지 기관 협,공문"]}
        self.assertEqual(_clean_risk_payload(payload)["evidence_needed"][1], "현지 기관 협의 공문")

    def setUp(self) -> None:
        self.indicator = {
            "id": "annual-1",
            "program": "응급의료 교육",
            "indicator": "교육과정 이수율",
            "target": "80%",
            "actual": "52%",
            "achievement_rate": 65.0,
            "evidence": "교육 결과보고서",
            "note": "2개 지역 자료 미제출",
            "status": "under",
            "evidence_document_ids": [],
        }

    def test_fallback_contains_concrete_target_actual_causes_and_actions(self) -> None:
        result = _fallback_performance_risk(self.indicator)

        self.assertIn("목표 80% 대비 실적 52%", result["risk_analysis"])
        self.assertTrue(any("2개 지역 자료 미제출" in item for item in result["root_causes"]))
        self.assertGreaterEqual(len(result["recommendations"]), 3)
        self.assertTrue(any("책임자" in item and "7일" in item for item in result["recommendations"]))
        self.assertIn("교육 결과보고서 원본", result["evidence_needed"])

    def test_unset_target_and_missing_mov_use_actionable_copy(self) -> None:
        indicator = {
            **self.indicator,
            "target": "-", "actual": "-", "achievement_rate": None,
            "status": "unset", "evidence": "PDM에 검증수단 미기재", "note": "",
        }

        result = _fallback_performance_risk(indicator)

        self.assertNotIn("목표 -", result["risk_analysis"])
        self.assertNotIn("미기재' 원본", " ".join(result["recommendations"]))
        self.assertIn("PDM 목표값", result["risk_analysis"])
        self.assertTrue(any("객관적 검증수단" in value for value in result["recommendations"]))
        self.assertIn("승인된 PDM 지표 정의서", result["evidence_needed"])

    @patch("kodame_intake.pdm_monitoring.analyze_performance_risks")
    def test_requested_refresh_overlays_ai_detail_and_records_provider(self, analyze) -> None:
        analyze.return_value = {
            "model": "test/model",
            "items": [{
                "id": "annual-1",
                "risk_title": "지역별 이수율 격차 위험",
                "risk_analysis": "목표 80% 대비 52%이며 두 지역 자료가 누락되었습니다.",
                "root_causes": ["2개 지역 자료 미제출"],
                "forecast": "누락이 지속되면 종료평가 근거가 제한됩니다.",
                "recommendations": ["지역 책임자가 7일 이내 결과보고서를 제출합니다."],
                "evidence_needed": ["지역별 교육 결과보고서"],
                "priority": "high",
                "analysis_source": "openrouter",
            }],
        }
        indicators = [dict(self.indicator)]

        metadata = _attach_performance_risk_analysis(indicators, analyze_risks=True)

        self.assertEqual(metadata["status"], "completed")
        self.assertEqual(metadata["provider"], "openrouter")
        self.assertEqual(metadata["model"], "test/model")
        self.assertEqual(indicators[0]["risk_analysis"]["analysis_source"], "openrouter")
        self.assertIn("지역별", indicators[0]["risk_analysis"]["risk_title"])

    @patch("kodame_intake.pdm_monitoring.analyze_performance_risks")
    def test_empty_ai_fields_do_not_remove_concrete_fallback(self, analyze) -> None:
        analyze.return_value = {
            "model": "test/model",
            "items": [{
                "id": "annual-1", "risk_title": "", "risk_analysis": "",
                "root_causes": [], "forecast": "", "recommendations": [],
                "evidence_needed": [], "priority": "high", "analysis_source": "openrouter",
            }],
        }
        indicators = [dict(self.indicator)]

        _attach_performance_risk_analysis(indicators, analyze_risks=True)

        detail = indicators[0]["risk_analysis"]
        self.assertIn("목표 80% 대비 실적 52%", detail["risk_analysis"])
        self.assertGreaterEqual(len(detail["recommendations"]), 3)


if __name__ == "__main__":
    unittest.main()
