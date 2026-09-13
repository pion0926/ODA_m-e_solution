import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from kodame_intake.pdm_evidence import apply_measurements, extract_measurements, enrich_from_evidence, _request_measurements
from kodame_intake.openrouter import AnalysisError


class EvidenceTests(unittest.TestCase):
    @patch("kodame_intake.pdm_evidence._request_json")
    def test_invalid_model_json_is_retried_with_a_bound(self, request):
        request.side_effect = [AnalysisError("invalid JSON"), ({"observations": []}, "test")]
        self.assertEqual(_request_measurements("system", "user", "test")[0], {"observations": []})
        self.assertEqual(request.call_count, 2)
        request.reset_mock()
        request.side_effect = AnalysisError("invalid JSON")
        with self.assertRaises(AnalysisError):
            _request_measurements("system", "user", "test")
        self.assertEqual(request.call_count, 3)

    def row(self):
        return {"id": "outcome-2-1", "indicator": "응급구조사 졸업시험 합격률(%)", "evidence": "자격시험 결과 보고서",
                "target": "80%", "actual": "-", "achievement_rate": None, "note": ""}

    def observation(self, value="97%"):
        return {"indicator_id": "outcome-2-1", "kind": "actual", "value": value, "quote": value, "period": "", "document_id": "doc"}

    def test_uploaded_result_recomputes_rate_and_preserves_provenance(self):
        row = self.row()
        apply_measurements(row, [self.observation()], [])
        self.assertEqual(row["actual"], "97%")
        self.assertEqual(row["achievement_rate"], 121.3)
        self.assertEqual(row["status"], "ok")
        self.assertIn("측정기간", row["note"])
        self.assertEqual(row["measurement_sources"][0]["document_id"], "doc")

    def test_duplicates_do_not_add_rates(self):
        row = self.row()
        apply_measurements(row, [self.observation(), self.observation()], [])
        self.assertEqual(row["actual"], "97%")

    def test_conflicts_and_failed_analysis_do_not_claim_success(self):
        for observations, errors in [([self.observation(), self.observation("50%")], []), ([self.observation()], ["unreadable"] )]:
            row = self.row()
            apply_measurements(row, observations, errors)
            self.assertIsNone(row["achievement_rate"])
            self.assertEqual(row["status"], "unset")

    def test_incompatible_units_are_not_divided(self):
        row = self.row()
        apply_measurements(row, [self.observation("300명")], [])
        self.assertIsNone(row["achievement_rate"])

    @patch("kodame_intake.pdm_evidence.extract_measurements")
    def test_pdm_assignments_and_monitoring_evidence_are_all_analyzed(self, extract):
        row = {**self.row(), "evidence_document_ids": ["monitoring-doc"]}
        documents = [{"id": key, "original_name": key, "extracted_path": "/unused"}
                     for key in ("pdm-doc", "monitoring-doc", "unrelated-doc")]
        extract.side_effect = lambda document, indicators: [{**self.observation(), "document_id": document["id"]}]
        result = enrich_from_evidence([row], documents, [("pdm-doc", row["id"], "outcome", "result", 0.9, "matched")])
        self.assertEqual(extract.call_count, 2)
        self.assertEqual(set(row["evidence_document_ids"]), {"pdm-doc", "monitoring-doc"})
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(row["actual"], "97%")
        self.assertEqual(row["achievement_rate"], 121.3)

    @patch("kodame_intake.pdm_evidence.connection")
    @patch("kodame_intake.pdm_evidence._request_json")
    def test_reads_end_of_long_document_and_rejects_ungrounded_values(self, request, connection):
        observation = self.observation()
        observation["quote"] = "합격률 97%"
        fabricated = {**observation, "value": "99%"}
        request.side_effect = [({"observations": []}, "test"), ({"observations": [observation, fabricated]}, "test")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.txt"
            path.write_text("가" * 29000 + "합격률 97%", encoding="utf-8")
            result = extract_measurements({"id": "doc", "original_name": "result.txt", "extracted_path": str(path)}, [self.row()])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["value"], "97%")
        self.assertEqual(request.call_count, 2)

    @patch("kodame_intake.pdm_evidence.connection")
    @patch("kodame_intake.pdm_evidence._request_json")
    def test_unchanged_content_reuses_cache(self, request, connection):
        request.return_value = ({"observations": []}, "test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.txt"
            path.write_text("자료 본문", encoding="utf-8")
            document = {"id": "doc", "original_name": "result.txt", "extracted_path": str(path)}
            extract_measurements(document, [self.row()])
            cached = connection.return_value.__enter__.return_value.execute.call_args.args[1][0].obj
            document["analysis"] = {"pdm_measurements": cached}
            extract_measurements(document, [self.row()])
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
