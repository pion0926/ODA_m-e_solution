import unittest
from unittest.mock import MagicMock,patch
from kodame_intake.api.report_routes import report_job_tray


class ReportTrayTests(unittest.TestCase):
    def test_partially_failed_report_is_not_shown_as_success(self):
        conn=MagicMock()
        conn.execute.return_value.fetchall.side_effect=[[],[]]
        conn.execute.return_value.fetchone.side_effect=[
            {'status':'completed_with_errors','progress':27,'total':27,'error_message':'7개 실패','message':None},None,None]
        with patch('kodame_intake.api.report_routes.connection') as connection:
            connection.return_value.__enter__.return_value=conn
            result=report_job_tray()['items']
        self.assertFalse(result[0]['active'])
        self.assertTrue(result[0]['failed'])

    def test_snapshot_tracks_sections_and_background_exports_without_document_text(self):
        conn=MagicMock()
        conn.execute.return_value.fetchall.side_effect=[
            [{'part_id':'summary','title':'요약','status':'generating','error_message':None}],
            [{'id':'test-translation','locale':'en','status':'running','error_message':None}]]
        conn.execute.return_value.fetchone.side_effect=[
            {'status':'running','progress':2,'total':27,'error_message':None,'message':'본문 작성'},
            {'status':'running','progress':10,'total':100,'error_message':None,'message':'슬라이드 작성'},
            {'status':'completed','progress':100,'total':100,'error_message':None,'message':'완료'}]
        with patch('kodame_intake.api.report_routes.connection') as connection:
            connection.return_value.__enter__.return_value=conn
            result=report_job_tray()['items']
        self.assertEqual([j['key'] for j in result if j['active']],['section:summary','translation:test-translation','report','presentation'])
        self.assertFalse(result[-1]['active'])
        self.assertTrue(all('content' not in j for j in result))
        self.assertIn('ORDER BY started_at',conn.execute.call_args_list[2].args[0])
