"""Optional document failures must not deadlock reviewed downstream work."""
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from kodame_intake.project_lifecycle import document_blocks_workflow, DOCUMENT_BLOCKS_WORKFLOW_SQL
from kodame_intake import dac_review, performance_review


class FailureIsolationTests(unittest.TestCase):
    def test_sql_and_preview_policy_agree_for_every_state_and_role(self):
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE docs(status TEXT,upload_role TEXT)')
            for role in ('evidence','project_plan','pdm'):
                for status in ('completed','failed','cancelled','queued','processing','retry','waiting_llm','awaiting_review'):
                    conn.execute('DELETE FROM docs')
                    conn.execute('INSERT INTO docs VALUES (?,?)',(status,role))
                    blocked = conn.execute(f'SELECT {DOCUMENT_BLOCKS_WORKFLOW_SQL} FROM docs').fetchone()[0]
                    self.assertEqual(bool(blocked),document_blocks_workflow({'status':status,'upload_role':role}))

    def test_dac_preview_excludes_failed_mapped_document_without_blocking_ready_documents(self):
        rows = [{'id':s,'original_name':s,'status':s,'upload_role':'evidence',
                 'analysis':{'dac_criteria':['effectiveness']}} for s in ('completed','failed','cancelled')]
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = [rows,[]]
        conn.execute.return_value.fetchone.return_value = None
        with patch.object(dac_review,'capture_input_snapshot',return_value={}):
            plan = dac_review.build_plan(conn)
        self.assertTrue(plan['ready'])
        self.assertEqual(plan['pending_count'],0)
        for question in plan['indicators']:
            self.assertNotIn('failed',question['document_ids'])
            self.assertNotIn('cancelled',question['document_ids'])
        self.assertTrue(any('completed' in q['document_ids'] for q in plan['indicators']))

    def test_performance_preview_still_ready_with_failed_and_cancelled_uploads(self):
        rows = [{'id':s,'original_name':s,'status':s,'upload_role':'evidence','progress':100}
                for s in ('completed','failed','cancelled')]
        rows.append({'id':'pdm','original_name':'pdm','status':'completed','upload_role':'pdm','progress':100,'analysis':{}})
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        conn.execute.return_value.fetchone.return_value = None
        model = {'tiers':[{'id':'outcome','name':'성과','indicators':[{'id':'i','text':'수료율','mov':'명단'}]}]}
        with patch.object(performance_review,'foundation_state',return_value={'ready':True}), \
             patch.object(performance_review,'capture_input_snapshot',return_value={}), \
             patch('kodame_intake.pdm_monitoring._model_from_slots',return_value=model), \
             patch('kodame_intake.pdm_monitoring._matches_pdm_requirement',return_value=(True,'')), \
             patch('kodame_intake.performance_delta.history',return_value={}):
            plan = performance_review.build_plan(conn)
        self.assertTrue(plan['ready'])
        self.assertEqual(plan['pending_count'],0)
        self.assertEqual(plan['indicators'][0]['document_ids'],['completed','pdm'])

    def test_export_does_not_treat_excluded_documents_as_processing(self):
        from kodame_intake import report_generator as reports
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [None, {'id':'run','status':'completed'},
            {'total':3,'completed':1,'processing':0}]
        conn.execute.return_value.fetchall.side_effect = [[],[]]
        with patch.object(reports,'connection') as connection, patch.object(reports,'_verified_execution_scope',return_value={}):
            connection.return_value.__enter__.return_value = conn
            result = reports.report_export_readiness()
        self.assertFalse(any(i['scope']=='documents' for i in result['issues']))
        self.assertTrue(any(i['scope']=='documents' for i in result['warnings']))
