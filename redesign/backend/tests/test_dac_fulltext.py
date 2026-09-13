import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from kodame_intake.dac_evidence import analyze_document, prepare_documents, _quote_matches, _validate_chunk
from kodame_intake.openrouter import AnalysisError
from kodame_intake.evaluation_runner import _corpus
from kodame_intake.parsers import parse_document


class DACFulltextTests(unittest.TestCase):
    def test_citations_are_copied_from_validated_source_line_ranges(self):
        item = {"question_id": "effectiveness-q2", "kind": "positive", "start_line": 2, "end_line": 2,
                "finding": "합격률 97%", "quote": "model paraphrase must not be used"}
        result = _validate_chunk({"evidence": [item]}, "제목\n합격률 97% (응시자 300명)\n끝", {"effectiveness-q2"})
        self.assertEqual(result[0]["quote"], "합격률 97% (응시자 300명)")
        with self.assertRaises(AnalysisError):
            _validate_chunk({"evidence": [{**item, "end_line": 20}]}, "한 줄", {"effectiveness-q2"})

    def test_ellipsis_requires_every_span_in_original_order(self):
        source = "학과 개설 승인을 완료했다. 중간 내용. 졸업시험 합격률 97%를 기록했다."
        self.assertTrue(_quote_matches("학과 개설 승인을 완료했다. ... 졸업시험 합격률 97%를 기록했다.", source))
        self.assertFalse(_quote_matches("학과 개설 승인을 완료했다. ... 졸업시험 합격률 100%를 기록했다.", source))
        self.assertFalse(_quote_matches("졸업시험 합격률 97%를 기록했다. ... 학과 개설 승인을 완료했다.", source))

    @patch("kodame_intake.parsers.MAX_EXTRACTED_CHARS", 20)
    def test_full_parser_reads_past_intake_limit_including_all_zip_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long.txt"
            path.write_text("a" * 30 + "END", encoding="utf-8")
            self.assertEqual(len(parse_document(path, ".txt")[0]), 20)
            self.assertTrue(parse_document(path, ".txt", full_text=True)[0].endswith("END"))
            archive = Path(folder) / "docs.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("one.txt", "a" * 40)
                output.writestr("two.txt", "LAST DOCUMENT")
            self.assertIn("LAST DOCUMENT", parse_document(archive, ".zip", full_text=True)[0])
            self.assertEqual(len(parse_document(path, ".txt")[0]), 20)

    def document(self, path):
        return {"id": "doc", "ref": "D001", "name": "results.txt", "summary": "old summary",
                "document_type": "report", "period": "", "organizations": [], "quality_flags": [],
                "assigned_criteria": ["effectiveness"], "extracted_path": str(path)}

    def evidence(self, quote):
        return {"question_id": "effectiveness-q2", "kind": "positive", "quote": quote, "finding": quote}

    @patch("kodame_intake.dac_evidence.connection")
    @patch("kodame_intake.dac_evidence._request_json")
    def test_all_chunks_including_last_page_reach_final_corpus(self, call, connection):
        call.side_effect = [({"evidence": []}, "test"), ({"evidence": []}, "test"),
                            ({"evidence": [self.evidence("합격률 97%")]}, "test")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long.txt"
            text = "가" * 50000 + "합격률 97%"
            path.write_text(text, encoding="utf-8")
            doc = self.document(path)
            prepare_documents([doc])
        review = doc["fulltext_review"]
        self.assertEqual(review["character_count"], len(text))
        self.assertEqual(review["chunks"][0]["start"], 0)
        self.assertEqual(review["chunks"][-1]["end"], len(text))
        self.assertTrue(all(a["end"] >= b["start"] for a, b in zip(review["chunks"], review["chunks"][1:])))
        corpus, refs = _corpus("effectiveness", [doc])
        self.assertEqual(corpus[0]["question_evidence"][0]["quote"], "합격률 97%")
        self.assertEqual(refs, {"D001": "doc"})
        self.assertNotIn("relevant_excerpt", corpus[0])

    @patch("kodame_intake.dac_evidence.connection")
    @patch("kodame_intake.dac_evidence._request_json")
    def test_false_quote_fails_instead_of_silently_completing(self, call, connection):
        call.return_value = ({"evidence": [self.evidence("합격률 100%")]}, "test")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.txt"
            path.write_text("합격률 97%", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "인용 근거"):
                analyze_document(self.document(path))
        self.assertEqual(call.call_count, 3)
        connection.assert_not_called()

    def test_missing_linked_body_blocks_scoring(self):
        doc = self.document("/does-not-exist.txt")
        with self.assertRaises(OSError):
            analyze_document(doc)
        with self.assertRaisesRegex(RuntimeError, "전체 본문"):
            _corpus("effectiveness", [doc])

    @patch("kodame_intake.dac_evidence.connection")
    @patch("kodame_intake.dac_evidence._request_json")
    def test_cache_reused_and_invalidated_when_content_changes(self, call, connection):
        call.return_value = ({"evidence": []}, "test")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.txt"
            path.write_text("내용", encoding="utf-8")
            doc = self.document(path)
            doc["dac_fulltext_cache"] = analyze_document(doc)
            analyze_document(doc)
            self.assertEqual(call.call_count, 1)
            path.write_text("추가 내용", encoding="utf-8")
            analyze_document(doc)
            self.assertEqual(call.call_count, 2)

    def test_unassigned_document_is_not_citable_evidence(self):
        doc = self.document("/unused")
        doc["assigned_criteria"] = []
        doc["fulltext_review"] = analyze_document(doc)
        corpus, refs = _corpus("effectiveness", [doc])
        self.assertFalse(corpus[0]["relevant_slot_assignment"])
        self.assertEqual(refs, {})


if __name__ == "__main__":
    unittest.main()
