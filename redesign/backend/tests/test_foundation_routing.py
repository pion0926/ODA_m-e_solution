import unittest
from unittest.mock import patch, MagicMock

from kodame_intake import project_overview, worker


class FoundationRoutingTests(unittest.TestCase):
    def test_current_overview_requires_exact_current_plan_source(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        self.assertIsNone(project_overview.latest_plan_overview(conn))
        sql = conn.execute.call_args.args[0]
        self.assertIn('o.source_document_ids=(', sql)
        self.assertIn("d.upload_role='project_plan'", sql)
        self.assertIn('jsonb_build_array(d.id::text)', sql)

    def test_pdm_upload_never_refreshes_overview(self):
        with patch.object(worker, 'refresh_pdm_model') as pdm, patch.object(worker, 'refresh_project_overview_if_needed') as overview:
            worker.refresh_uploaded_foundation('pdm')
            pdm.assert_called_once_with(analyze_risks=False)
            overview.assert_not_called()

    def test_plan_upload_never_refreshes_pdm(self):
        with patch.object(worker, 'refresh_pdm_model') as pdm, patch.object(worker, 'refresh_project_overview_if_needed') as overview:
            worker.refresh_uploaded_foundation('project_plan')
            overview.assert_called_once_with(force=True)
            pdm.assert_not_called()

    def test_general_upload_never_refreshes_either_foundation(self):
        with patch.object(worker, 'refresh_pdm_model') as pdm, patch.object(worker, 'refresh_project_overview_if_needed') as overview:
            worker.refresh_uploaded_foundation('evidence')
            pdm.assert_not_called()
            overview.assert_not_called()

    def test_plan_source_is_explicit_latest_completed_role(self):
        rows = [dict(id='plan', original_name='원문.pdf', summary='사업계획서 내용', analysis={}, queue_position=7, upload_role='project_plan')]
        with patch.object(project_overview, 'connection') as connection:
            conn = connection.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = rows
            result = project_overview._documents()
            sql = conn.execute.call_args.args[0]
            self.assertIn("status='completed' AND upload_role='project_plan'", sql)
            self.assertIn('active_intake_documents', sql)
            self.assertIn('ORDER BY queue_position DESC LIMIT 1', sql)
        self.assertEqual([r['id'] for r in result], ['plan'])

    def test_no_fallback_even_if_pdm_or_evidence_claims_plan_classification(self):
        for role in ('pdm', 'evidence'):
            with self.subTest(role=role), patch.object(project_overview, 'connection') as connection:
                conn = connection.return_value.__enter__.return_value
                conn.execute.return_value.fetchall.return_value = [dict(upload_role=role, analysis={'content_classification':{'is_project_plan':True}})]
                self.assertEqual(project_overview._documents(), [])

    def test_no_plan_means_no_ai_or_overview_write(self):
        with patch.object(project_overview, '_documents', return_value=[]), patch.object(project_overview, 'request_overview') as ai, patch.object(project_overview, 'connection') as conn:
            with self.assertRaisesRegex(RuntimeError, '분석 완료된 사업계획서'):
                project_overview.generate_project_overview()
            ai.assert_not_called()
            conn.assert_not_called()

    def test_overview_prompt_and_saved_sources_use_plan_only(self):
        plan = dict(ref='D001',id='plan',name='사업계획서',title='사업계획',type='계획서',period='2026',organizations=[],summary='계획서에만 있는 사실',quality_flags=[])
        with patch.object(project_overview, '_documents', return_value=[plan]), patch.object(project_overview, 'OPENROUTER_API_KEY', 'test'), patch.object(project_overview, 'current_llm_model', return_value='test'), patch.object(project_overview, 'request_overview', return_value={}) as ai, patch.object(project_overview, 'connection') as connection:
            project_overview.generate_project_overview()
            self.assertIn('사업계획서의 정보만 근거', ai.call_args.args[0])
            self.assertEqual(ai.call_args.args[1], {'D001'})
            conn = connection.return_value.__enter__.return_value
            self.assertEqual(conn.execute.call_args.args[1][5].obj, ['plan'])
