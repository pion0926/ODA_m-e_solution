import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from kodame_intake.dac_pdm import build_context, attach_question_context, refresh_context


class DACPDMLinkingTests(unittest.TestCase):
    def context(self):
        return build_context({"id": "snapshot", "created_at": datetime.now(timezone.utc),
            "source_document_id": "pdm", "source_file_name": "PDM.pdf", "model": {
                "tiers": [{"id": "outcome", "assumption": "제도 지속"}],
                "performance_source_document_id": "annual",
                "performance_indicators": [{"id": "outcome-2-1", "indicator": "졸업시험 합격률",
                    "target": "80%", "actual": "97%", "achievement_rate": 121.3, "note": "측정기간 미기재",
                    "evidence_document_ids": ["txt"], "measurement_sources": [{"document_id": "txt", "file_name": "합격률.txt",
                        "quote": "97% (응시자 수 300명)", "value": "97%"}]}],
                "risk_analysis": {"status": "completed"}}}, [],
            [{"id": key, "ref": ref} for key, ref in [("pdm", "D001"), ("annual", "D002"), ("txt", "D003"), ("other", "D004")]])

    def test_full_pdm_values_assumptions_and_provenance_are_preserved(self):
        context = self.context()
        metric = context["model"]["performance_indicators"][0]
        self.assertEqual((metric["target"], metric["actual"], metric["achievement_rate"]), ("80%", "97%", 121.3))
        self.assertEqual(context["model"]["tiers"][0]["assumption"], "제도 지속")
        self.assertEqual(context["evidence_document_refs"], {"D001": "pdm", "D002": "annual", "D003": "txt"})
        self.assertIn("risk_analysis", context["model"])

    def test_using_pdm_indicator_attaches_actual_source_without_changing_score(self):
        question = {"question_id": "effectiveness-q2", "pdm_indicator_ids": ["outcome-2-1"],
                    "evidence_quotes": [], "evidence_document_ids": [], "score": 3}
        attach_question_context(question, self.context())
        self.assertEqual(question["evidence_quotes"][0]["quote"], "97% (응시자 수 300명)")
        self.assertEqual(question["evidence_document_ids"], ["txt"])
        self.assertEqual(question["score"], 3)
        self.assertEqual(question["pdm_context"]["snapshot_id"], "snapshot")

    def test_unknown_pdm_indicator_cannot_be_cited(self):
        with self.assertRaises(RuntimeError):
            attach_question_context({"pdm_indicator_ids": ["invented"]}, self.context())

    @patch("kodame_intake.dac_pdm.refresh_pdm_model")
    def test_absent_pdm_is_explicit_and_not_zero(self, refresh):
        context = refresh_context([{"name": "results.txt"}])
        self.assertEqual(context["status"], "unavailable")
        self.assertEqual(context["model"], {})
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
