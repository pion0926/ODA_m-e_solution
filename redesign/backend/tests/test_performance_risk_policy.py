import unittest
from copy import deepcopy
from unittest.mock import patch

from kodame_intake.performance_risk_policy import validate_risk_result
from kodame_intake.reported_metrics_source import select_reported_metrics_source


class RiskQualityTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [{"id": "outcome-1", "status": "unset"}]
        self.result = {"items": [{"id": "outcome-1", "risk_title": "측정 근거 미확인",
            "risk_analysis": "등록 자료에서 실적과 측정일을 확인할 수 없어 판단이 제한됨.",
            "forecast": "추가 근거 미확보 시 평가 판단이 제한될 수 있음.",
            "root_causes": ["자료 미등록 원인 확인 필요"],
            "recommendations": ["권고 담당: 성과관리 담당자. 검토 착수 후 7일 이내 측정일과 원자료를 확인함."],
            "evidence_needed": ["측정일이 기재된 집계 원자료"]}]}

    def test_relative_advice_and_missing_evidence_are_valid(self):
        validate_risk_result(self.result, self.candidates)

    def test_invented_calendar_deadline_is_rejected(self):
        for date in ("2024년 11월 30일까지", "2027-01-01까지", "11월 30일까지"):
            result = deepcopy(self.result)
            result["items"][0]["recommendations"] = [date + " 수행함."]
            with self.assertRaises(ValueError):
                validate_risk_result(result, self.candidates)

    def test_missing_evidence_is_not_management_failure(self):
        self.result["items"][0]["risk_analysis"] = "실적 증빙이 없어 성과 관리가 이루어지지 않고 있다."
        with self.assertRaises(ValueError):
            validate_risk_result(self.result, self.candidates)

    def test_missing_or_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            validate_risk_result({"items": []}, self.candidates)

    def test_metrics_source_uses_schema_not_year_or_project(self):
        document = {"original_name": "신규국가_분기실적.xlsx", "extracted_path": "/input.txt"}
        with patch("pathlib.Path.read_text", return_value="프로그램 | 성과지표 | 목표 | 실적 | 달성도 | 산출근거 | 비고\n교육 | 수료자 수 | 5 | 4 | 0.8 | 명부 | 진행"):
            source, text = select_reported_metrics_source([document])
        self.assertEqual(source, document)
        self.assertIn("수료자", text)
        with patch("pathlib.Path.read_text", return_value="예산표 | 지출액 | 기타"):
            self.assertEqual(select_reported_metrics_source([document]), (None, ""))
