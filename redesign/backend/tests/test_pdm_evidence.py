import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from kodame_intake.pdm_evidence import apply_measurements, extract_measurements, enrich_from_evidence, _request_measurements
from kodame_intake.openrouter import AnalysisError


class EvidenceTests(unittest.TestCase):
    @patch('kodame_intake.pdm_evidence.connection')
    @patch('kodame_intake.pdm_evidence._request_json')
    def test_unsupported_ai_suggestion_is_a_recorded_limitation_not_failed_generation(self, request, connection):
        request.return_value=({'observations':[{'indicator_id':self.row()['id'],'kind':'actual','value':'99%',
                                              'quote':'합격률 80%','period':''}],
                              'reviews':[{'indicator_id':self.row()['id'],'status':'found','reason':'수치 제안'}]},'test')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.txt';path.write_text('합격률 80%',encoding='utf-8')
            doc={'id':'doc','original_name':'result.txt','extracted_path':str(path)}
            assert extract_measurements(doc,[self.row()])==[]
        cached=doc['analysis']['pdm_measurements']
        assert cached['unverified_indicator_ids']==[]
        assert cached['reviews'][0]['verification_warning'] is True
        assert cached['reviews'][0]['status']=='no_measurement'
        assert '수치가' in cached['rejected_observations'][0]['exclusion_reason']

    @patch('kodame_intake.pdm_evidence.connection')
    @patch('kodame_intake.pdm_evidence._request_json')
    def test_exact_source_id_supports_categorical_foreign_language_approval(self, request, connection):
        import json
        row={'id':'approval','indicator':'표준 교육과정 승인 여부(유/무)','evidence':'교육부 승인서'}
        def response(system,prompt,title,**kwargs):
            source=json.loads(prompt)['sources'][0]
            return {'observations':[{'indicator_id':'approval','kind':'actual','value':'유',
                    'source_id':source['source_id'],'period':''}],
                    'reviews':[{'indicator_id':'approval','status':'found','reason':'승인 사실 명시'}]},'test'
        request.side_effect=response
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'approval.txt'; path.write_text('Ministry approved this curriculum.',encoding='utf-8')
            document={'id':'doc','original_name':'approval.txt','extracted_path':str(path)}
            result=extract_measurements(document,[row])
        self.assertEqual(result[0]['value'],'유')
        self.assertEqual(result[0]['quote'],'Ministry approved this curriculum.')
        self.assertEqual(document['analysis']['pdm_measurements']['unverified_indicator_ids'],[])

    @patch('kodame_intake.pdm_evidence.connection')
    @patch('kodame_intake.pdm_evidence._request_json')
    def test_equivalent_count_label_preserves_reported_values_and_review(self,request,connection):
        row={'id':'outputs-3-1-1','indicator':'양성된 지역사회 CPCR 전문 강사 수 (명)','evidence':'강사 자격증 발급 대장'}
        quote='CPCR 강사 양성여부(명) | 10명 | 6명'
        observations=[{'indicator_id':row['id'],'kind':kind,'value':value,'quote':quote,'period':''} for kind,value in [('target','10명'),('actual','6명')]]
        reviews=[{'indicator_id':row['id'],'status':'found','reason':'동일한 강사 양성 인원 보고'}]
        request.return_value=({'observations':observations,'reviews':reviews},'test')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'metrics.txt';path.write_text('성과지표 | 목표 | 실적\n'+quote,encoding='utf-8')
            doc={'id':'doc','original_name':'metrics.txt','extracted_path':str(path)}
            result=extract_measurements(doc,[row])
        self.assertEqual([o['value'] for o in result],['10명','6명'])
        self.assertEqual(doc['analysis']['pdm_measurements']['reviews'][0]['reason'],reviews[0]['reason'])
        schema=request.call_args.kwargs['response_schema']
        self.assertEqual(schema['properties']['observations']['items']['properties']['indicator_id']['enum'],[row['id']])

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
        reviews=[{'indicator_id':self.row()['id'],'status':'no_measurement','reason':'본문에 해당 값 없음'}]
        request.side_effect = [({"observations": [],'reviews':reviews}, "test"), ({"observations": [observation, fabricated],'reviews':reviews}, "test")]
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
        request.return_value = ({"observations": [],'reviews':[{'indicator_id':self.row()['id'],'status':'no_measurement','reason':'직접 측정값 없음'}]}, "test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.txt"
            path.write_text("자료 본문", encoding="utf-8")
            document = {"id": "doc", "original_name": "result.txt", "extracted_path": str(path)}
            extract_measurements(document, [self.row()])
            cached = connection.return_value.__enter__.return_value.execute.call_args.args[1][0].obj
            document["analysis"] = {"pdm_measurements": cached}
            extract_measurements(document, [self.row()])
        self.assertEqual(request.call_count, 1)

    @patch("kodame_intake.pdm_evidence.connection")
    @patch("kodame_intake.pdm_evidence._request_json")
    def test_retry_reuses_same_pair_cache_after_another_indicator_was_processed(self, request, connection):
        def response(system,prompt,title,**kwargs):
            import json
            rows=json.loads(prompt)['indicators']
            return {'observations':[], 'reviews':[{'indicator_id':row['id'],'status':'no_measurement','reason':'직접 값 미확인'} for row in rows]},'test'
        request.side_effect=response
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.txt';path.write_text('검토할 자료 본문',encoding='utf-8')
            document={'id':'doc','original_name':'data.txt','extracted_path':str(path)}
            extract_measurements(document,[self.row()])
            extract_measurements(document,[{**self.row(),'id':'other'}])
            extract_measurements(document,[self.row()])
        self.assertEqual(request.call_count,2)
        self.assertEqual(document['analysis']['pdm_measurements']['reviews'][0]['indicator_id'],self.row()['id'])


if __name__ == "__main__":
    unittest.main()
