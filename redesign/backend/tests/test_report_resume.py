import unittest
from unittest.mock import MagicMock, patch

from kodame_intake.report_resume import resumable_parts
from kodame_intake import report_generator as generator

SNAPSHOT = {"document_digest": "documents-a", "evaluation_run_id": "eval-a"}


def section(part, run="old", status="draft", snapshot=None):
    return {"part_id": part, "status": status, "content": "saved report",
            "generation_metadata": {"generation_run_id": run, "input_snapshot": snapshot or SNAPSHOT}}


class ReportRecoveryTests(unittest.TestCase):
    def test_resume_skips_only_successful_same_run_and_inputs(self):
        run = {"id": "old", "status": "failed", "input_snapshot": SNAPSHOT}
        rows = [section("success"), section("failed", status="failed"),
                section("unrelated", run="other"),
                section("stale", snapshot={**SNAPSHOT, "document_digest": "changed"})]
        self.assertEqual(resumable_parts(run, rows, SNAPSHOT), ["success"])

    def test_repeated_resume_keeps_inherited_successes(self):
        run = {"id": "new", "status": "cancelled", "input_snapshot": SNAPSHOT, "resume_part_ids": ["first"]}
        self.assertEqual(resumable_parts(run, [section("first"), section("second", "new")], SNAPSHOT), ["first", "second"])

    def test_reject_changed_data_evaluation_active_and_legacy_runs(self):
        run = {"id": "old", "status": "failed", "input_snapshot": SNAPSHOT}
        for modified in ({**run, "input_snapshot": None}, {**run, "status": "running"},
                         {**run, "input_snapshot": {**SNAPSHOT, "evaluation_run_id": "older"}}):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                resumable_parts(modified, [], SNAPSHOT)

    def test_worker_does_not_call_ai_for_saved_sections(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"resume_part_ids": ["a", "b"]}
        with patch.object(generator, "connection") as pool, patch.object(generator, "check_cancelled"), \
             patch.object(generator, "GENERATION_ORDER", ["a", "b", "c"]), \
             patch.object(generator, "_generate_report_section", return_value={"part_id": "c", "status": "draft"}) as generate:
            pool.return_value.__enter__.return_value = conn
            result = generator._generate_all_report_sections("new")
        generate.assert_called_once_with("c")
        self.assertEqual(len(result), 3)

    def test_global_limit_stops_batch_without_failing_later_sections(self):
        from kodame_intake.ai.job_budget import BudgetExceeded
        with patch.object(generator, 'GENERATION_ORDER', ['a','b','c']), \
             patch.object(generator, 'check_cancelled'), \
             patch.object(generator, '_generate_report_section', side_effect=[
                 {'part_id':'a','status':'draft'}, BudgetExceeded('token limit')]) as generate:
            with self.assertRaises(BudgetExceeded):
                generator._generate_all_report_sections()
        self.assertEqual([c.args[0] for c in generate.call_args_list], ['a','b'])
