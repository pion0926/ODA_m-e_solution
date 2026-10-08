import unittest
from unittest.mock import Mock
from kodame_intake.report_recovery import repair_recovery_response
from kodame_intake.report_sources import ensure_authoritative_pdm_notice


class ReportRecoveryTests(unittest.TestCase):
    def test_pdm_identity_is_verified_metadata_and_idempotent(self):
        context = {'authoritative_pdm': {'source_label': '최신 사업설계매트릭스(PDM)'}}
        content = '- [outcome-1] 확인 필요'
        result = ensure_authoritative_pdm_notice(content, context)
        self.assertIn(context['authoritative_pdm']['source_label'], result)
        self.assertTrue(result.endswith(content))
        self.assertEqual(ensure_authoritative_pdm_notice(result, context), result)
        self.assertEqual(ensure_authoritative_pdm_notice(content, {}), content)
        self.assertEqual(ensure_authoritative_pdm_notice('', context), '')

    def test_valid_recovery_is_not_rewritten(self):
        repair = Mock()
        result = repair_recovery_response('valid', lambda _: [], repair, str.strip)
        self.assertEqual(result, ('valid', [], 0))
        repair.assert_not_called()

    def test_actual_failure_is_fed_back_and_rechecked(self):
        repair = Mock(return_value='  evidence and limitations  ')
        result = repair_recovery_response('short', lambda s: ['length'] if len(s) < 15 else [], repair, str.strip)
        self.assertEqual(result, ('evidence and limitations', [], 1))
        repair.assert_called_once_with('short', ['length'])

    def test_invalid_recovery_never_waives_contract(self):
        repair = Mock(return_value='still invalid')
        result = repair_recovery_response('original', lambda _: ['invalid'], repair, str.strip)
        self.assertEqual(result[1:], (['invalid'], 2))
        self.assertEqual(repair.call_count, 2)

    def test_empty_repair_retains_last_candidate_and_error(self):
        result = repair_recovery_response('original', lambda _: ['invalid'], lambda *_: '', str.strip)
        self.assertEqual(result, ('original', ['invalid'], 1))
