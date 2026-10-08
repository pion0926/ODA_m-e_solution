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
    @patch('kodame_intake.parsers._pdf_ocr',return_value='실제 OCR 본문')
    @patch('kodame_intake.parsers.PdfReader')
    def test_page_markers_do_not_hide_image_only_document(self, reader, ocr):
        from unittest.mock import MagicMock
        reader.return_value.is_encrypted=False
        reader.return_value.pages=[MagicMock() for _ in range(12)]
        for page in reader.return_value.pages:
            page.extract_text.return_value=''
        self.assertEqual(parse_document(Path('/unused.pdf'),'.pdf',full_text=True)[0],'실제 OCR 본문')
        ocr.assert_called_once()

    def test_long_citation_is_split_without_losing_original_evidence(self):
        text='\n'.join(['가'*1000,'나'*1000,'다'*1000,'부정적 결과 '+ '라'*1000])
        result=_validate_chunk({'evidence':[{'question_id':'effectiveness-q3','kind':'context',
            'start_line':1,'end_line':4,'finding':'전체 구간을 대조한 제안'}]},text,{'effectiveness-q3'})
        self.assertGreater(len(result),1)
        self.assertTrue(all(len(e['quote'])<=2000 and e['quote'] in text for e in result))
        self.assertEqual(''.join(e['quote'].replace('\n','').replace(' ','') for e in result),text.replace('\n','').replace(' ',''))
        self.assertEqual(len({e['quote_group'] for e in result}),1)
        self.assertTrue(any('부정적 결과' in e['quote'] for e in result))

    def test_long_ellipsis_quotes_resolve_to_real_spans_and_false_quotes_still_fail(self):
        text='가'*2200+' 생략 구간 '+'나'*2200
        item={'question_id':'effectiveness-q3','kind':'context','quote':'가'*2200+' ... '+'나'*2200,'finding':'두 구간 대조'}
        result=_validate_chunk({'evidence':[item]},text,{'effectiveness-q3'})
        self.assertTrue(all(e['quote'] in text and len(e['quote'])<=2000 for e in result))
        with self.assertRaises(AnalysisError):
            _validate_chunk({'evidence':[{**item,'quote':'가'*2200+'없는 원문'+'나'*2200}]},text,{'effectiveness-q3'})

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json')
    def test_bad_large_response_retries_smaller_windows_without_skipping_text(self, call, conn):
        import json
        def response(system,prompt,*args,**kwargs):
            data=json.JSONDecoder().raw_decode(prompt)[0]
            if data['chunk_end']-data['chunk_start']>6000:
                raise AnalysisError('잘못된 응답 형식')
            return {'evidence':[]},'test'
        call.side_effect=response
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'long.txt';path.write_text('가'*12000,encoding='utf-8')
            result=analyze_document(self.document(path))
        ranges=sorted((c['start'],c['end']) for c in result['chunks'])
        self.assertEqual(ranges[0][0],0)
        self.assertEqual(ranges[-1][1],12000)
        self.assertTrue(all(a[1]>=b[0] for a,b in zip(ranges,ranges[1:])))
        self.assertTrue(all(end-start<=6000 for start,end in ranges))

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
        saved = connection.return_value.__enter__.return_value.execute.call_args.args[1][0].obj
        self.assertEqual(saved['status'],'partial')
        self.assertEqual(saved['chunks'],[])
        self.assertEqual(len(saved['failed_windows']),1)

    def test_missing_linked_body_blocks_scoring(self):
        doc = self.document("/does-not-exist.txt")
        with self.assertRaises(OSError):
            analyze_document(doc)
        from kodame_intake.dac_assessor import assess_criterion
        from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
        corpus, _ = _corpus("effectiveness", [doc])
        with patch('kodame_intake.dac_assessor._request_json') as request:
            with self.assertRaisesRegex(RuntimeError, "원문 검토 미완료"):
                assess_criterion('effectiveness', EVALUATION_CRITERIA['effectiveness'], corpus, {},
                                 {'status': 'unavailable', 'model': {}})
        request.assert_not_called()

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

    @patch('kodame_intake.dac_evidence.connection')
    @patch('kodame_intake.dac_evidence._request_json')
    def test_new_intake_reviews_unassigned_document_against_all_criteria(self, call, connection):
        call.return_value=({'evidence':[self.evidence('합격률 97%')]},'test')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'new-evidence.txt'
            path.write_text('합격률 97%',encoding='utf-8')
            doc=self.document(path);doc.update(assigned_criteria=[],review_all=True)
            prepare_documents([doc])
            corpus,refs=_corpus('effectiveness',[doc])
        self.assertEqual(refs,{'D001':'doc'})
        self.assertEqual(len(doc['fulltext_review']['reviewed_criteria']),5)
        self.assertIn('effectiveness-q2',doc['fulltext_review']['question_ids'])
        self.assertEqual(corpus[0]['question_evidence'][0]['quote'],'합격률 97%')


if __name__ == "__main__":
    unittest.main()
