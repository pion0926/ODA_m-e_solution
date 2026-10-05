import unittest
from unittest.mock import patch
from kodame_intake import intake_triage as triage


class IntakeTriageTests(unittest.TestCase):
    def test_bounded_sample_covers_start_middle_and_end(self):
        text='A'*30000+'B'*30000+'C'*30000
        sample=triage.sample_text(text)
        self.assertLess(len(sample),16100)
        self.assertTrue(sample.startswith('A'*10000))
        self.assertIn('B'*3000,sample)
        self.assertTrue(sample.endswith('C'*3000))

    def test_automatic_and_uncertain_routes(self):
        for kind, confidence, expected in [('artifact',.95,'artifact'),('evidence',.95,'evidence'),('artifact',.7,'artifact'),('evidence',.7,'artifact'),('mixed',.99,'artifact'),('uncertain',.99,'artifact')]:
            with self.subTest(kind=kind,confidence=confidence), patch.object(triage,'_request_json',return_value=({'kind':kind,'confidence':confidence},'model')) as call:
                result=triage.classify('book.txt','text '*50000)
                self.assertFalse(result['needs_review'])
                self.assertEqual(result['kind'],expected)
                self.assertEqual(result['suggested_kind'],kind)
                self.assertFalse(result['project_production_verified'])
                self.assertLess(len(call.call_args.args[1]),17000)

    def test_small_text_preserved(self):
        self.assertEqual(triage.sample_text('chapter'),'chapter')

    def test_saved_ambiguous_route_is_resolved_idempotently(self):
        old = {'kind':'mixed','confidence':.9,'needs_review':True}
        new = triage.resolve_route(old)
        self.assertEqual(new['kind'],'artifact')
        self.assertFalse(new['needs_review'])
        self.assertEqual(triage.resolve_route(new),new)
