import copy
import unittest
from fastapi import HTTPException
from kodame_intake.performance_review import validate_selection


class PerformanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'ready': True, 'message': 'ready', 'revision': 'r' * 64,
                     'source_document_id': 'pdm', 'source_file_name': 'pdm.txt',
                     'input_snapshot': {'document_digest': 'digest'},
                     'indicators': [{'id': 'outcome-1'}, {'id': 'outputs-1'}],
                     'documents': [{'id': 'a', 'status': 'completed'}, {'id': 'b', 'status': 'completed'}]}

    def test_explicit_selection_is_frozen_including_empty_indicators(self):
        selection = {'outcome-1': ['b'], 'outputs-1': []}
        result = validate_selection(self.plan, self.plan['revision'], selection)
        selection['outcome-1'].append('a')
        self.assertEqual(result['mappings'], {'outcome-1': ['b'], 'outputs-1': []})

    def test_stale_preview_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            validate_selection(self.plan, 'old', {'outcome-1': [], 'outputs-1': []})
        self.assertEqual(error.exception.status_code, 409)

    def test_foreign_pending_duplicate_or_unknown_mapping_rejected(self):
        for mappings in ({'outcome-1': ['foreign'], 'outputs-1': []},
                         {'outcome-1': ['a', 'a'], 'outputs-1': []},
                         {'outcome-1': []}, {'unknown': [], 'outputs-1': []}):
            with self.subTest(mappings=mappings), self.assertRaises(HTTPException):
                validate_selection(self.plan, self.plan['revision'], mappings)

    def test_pending_upload_cannot_be_started(self):
        plan = copy.deepcopy(self.plan); plan['ready'] = False
        with self.assertRaises(HTTPException):
            validate_selection(plan, plan['revision'], {'outcome-1': [], 'outputs-1': []})
