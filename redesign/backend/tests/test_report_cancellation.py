import unittest
from unittest.mock import MagicMock, patch

from kodame_intake import report_cancellation as cancel
from kodame_intake import report_generator as generator
from kodame_intake.api import report_routes as main
from fastapi import HTTPException, BackgroundTasks
from types import SimpleNamespace


class ReportCancellationTests(unittest.TestCase):
    def test_cancel_unknown_or_other_project_run_is_404(self):
        with patch.object(main, 'connection') as pool:
            pool.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            with self.assertRaises(HTTPException) as error:
                main.cancel_report_generation('unknown')
            self.assertEqual(error.exception.status_code, 404)

    def test_presentation_uses_dedicated_model_in_row_and_background(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{'total':27, 'completed':27}, None]
        jobs = BackgroundTasks()
        request = SimpleNamespace(state=SimpleNamespace(auth={'account_id':'account'}, llm_model='google/gemini-3.8-flash'))
        with patch.object(main, 'enqueue') as enqueue, patch.object(main, 'connection') as pool, patch.object(main, '_reserve_project_workflow'), patch.object(main, 'project_lifecycle', return_value={'report_current':True}), patch.object(main, 'require_available_model', return_value='openai/gpt-6-astra'), patch.object(main, 'OPENROUTER_API_KEY', 'test'), patch.object(main, 'current_project_id', return_value='project'):
            pool.return_value.__enter__.return_value = conn
            result = main.start_presentation_export(jobs, request)
        self.assertEqual(result['model'], 'openai/gpt-6-astra')
        self.assertEqual(jobs.tasks, [])
        self.assertEqual(enqueue.call_args.args[3], 'openai/gpt-6-astra')
        self.assertIn('openai/gpt-6-astra', conn.execute.call_args.args[1])

    def test_cancel_is_scoped_and_missing_run_does_not_cancel(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'cancel_requested': True}
        with patch.object(cancel, 'connection') as pool:
            pool.return_value.__enter__.return_value = conn
            cancel.check_cancelled()
            conn.execute.assert_not_called()
            with cancel.generation_run('run'):
                with self.assertRaises(cancel.ReportCancelled):
                    cancel.check_cancelled()
            cancel.check_cancelled()

    def test_cancel_prevents_paid_call(self):
        with patch.object(generator, 'check_cancelled', side_effect=cancel.ReportCancelled()), patch.object(generator.httpx, 'Client') as client:
            with self.assertRaises(cancel.ReportCancelled):
                generator._call_json('system', 'prompt', 'test', 0.2)
            client.assert_not_called()

    def test_cancel_stops_batch_before_next_section(self):
        with patch.object(generator, 'check_cancelled', side_effect=[None, cancel.ReportCancelled()]), patch.object(generator, '_generate_report_section', return_value={'status':'draft'}) as section:
            with self.assertRaises(cancel.ReportCancelled):
                generator._generate_all_report_sections()
            self.assertEqual(section.call_count, 1)

    def test_cancelled_section_preserves_previous_content_and_status(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'status':'draft', 'content':'saved', 'error_message':None}
        with patch.object(generator, 'connection') as pool, patch('kodame_intake.project_lifecycle.capture_input_snapshot', side_effect=cancel.ReportCancelled()):
            pool.return_value.__enter__.return_value = conn
            with self.assertRaises(cancel.ReportCancelled):
                generator._generate_report_section('summary-ko')
        sql, params = conn.execute.call_args.args
        self.assertNotIn('content=', sql)
        self.assertEqual(params[0], 'draft')


if __name__ == '__main__':
    unittest.main()
