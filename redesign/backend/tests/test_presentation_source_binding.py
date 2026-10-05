import unittest
from kodame_intake.presentation_reference_prompt import bind_page_sources


class SourceBindingTests(unittest.TestCase):
    def test_only_relevant_evidence_is_sent_not_conversion_tree(self):
        from kodame_intake.presentation_reference_prompt import scoped_evidence
        source={'structured_evidence':{'hwpx_conversion_contract':{'large':'not for LLM'},'evaluation_run':{'criteria':[
            {'criterion_id':'relevance','score':3},{'criterion_id':'efficiency','score':2}]}},'evidence_catalog':[
            {'file_name':'included','summary':'complete summary','used_by_sections':['criteria-relevance']},
            {'file_name':'unrelated','summary':'other','used_by_sections':['feedback']}]}
        structured,catalog=scoped_evidence(source,{'criteria-relevance'})
        self.assertEqual(len(structured['criteria']),1)
        self.assertEqual([r['file_name'] for r in catalog],['included'])
        self.assertNotIn('conversion',str(structured))

    def test_checkpoint_changes_with_model_evidence_and_photo(self):
        from kodame_intake.presentation_reference_export import checkpoint_key,save_checkpoint
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        base=checkpoint_key({'version':1},{'text':'same'},{},'model-a')
        for source,photos,model in [({'text':'new'},{},'model-a'),({'text':'same'},{},'model-b'),({'text':'same'},{'p':{'data':b'new photo'}},'model-a')]:
            self.assertNotEqual(base,checkpoint_key({'version':1},source,photos,model))
        with TemporaryDirectory() as root:
            path=Path(root)/'project/checkpoint.json';save_checkpoint(path,[{'slide_number':1}],[{'attempt':1}])
            self.assertEqual(json.loads(path.read_text())['slides'][0]['slide_number'],1)
            self.assertFalse(path.with_suffix('.tmp').exists())

    def test_fixed_page_sources_do_not_depend_on_generated_aliases(self):
        raw={'slides':[{'slide_number':7,'source_sections':['evaluation-matrix']}]}
        pages=[{'slide_number':7,'source_sections':['eval-matrix']}]
        source={'report_sections':[{'part_id':'eval-matrix','content':'saved matrix'}]}
        result=bind_page_sources(raw,pages,source)
        self.assertEqual(result['slides'][0]['source_sections'],['eval-matrix'])

    def test_missing_or_empty_actual_source_is_not_invented(self):
        for content in ['',None]:
            with self.subTest(content=content),self.assertRaises(ValueError):
                bind_page_sources({'slides':[{'slide_number':7}]},[{'slide_number':7,'source_sections':['eval-matrix']}],{'report_sections':[{'part_id':'eval-matrix','content':content}]})

    def test_wrong_pages_are_not_repaired_as_if_valid(self):
        with self.assertRaises(ValueError):
            bind_page_sources({'slides':[{'slide_number':8}]},[{'slide_number':7,'source_sections':['eval-matrix']}],{'report_sections':[]})
