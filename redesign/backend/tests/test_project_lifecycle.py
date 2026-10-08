import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from kodame_intake.project_lifecycle import (
    evaluate_freshness, input_snapshot_from_rows, recover_interrupted_sections, snapshots_match,
)


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        self.docs = [{"id": "doc-1", "sha256": "first", "status": "completed", "updated_at": self.now}]
        self.run = {"id": "run-1", "status": "completed", "document_count": 1,
                    "started_at": self.now + timedelta(minutes=1), "completed_at": self.now + timedelta(minutes=2)}
        self.snapshot = input_snapshot_from_rows(self.docs, self.run)
        self.run["input_snapshot"] = input_snapshot_from_rows(self.docs)
        self.sections = [{"part_id": "summary-ko", "status": "draft", "content": "본문",
                          "generation_metadata": {"input_snapshot": self.snapshot},
                          "generated_at": self.now + timedelta(minutes=3)}]

    def state(self, docs=None, run=None, sections=None):
        selected = self.run if run is None else run
        return evaluate_freshness(input_snapshot_from_rows(self.docs if docs is None else docs, selected), selected,
                                  self.sections if sections is None else sections)

    def test_empty_project_never_looks_ready(self):
        state = evaluate_freshness(input_snapshot_from_rows([]), None, [])
        self.assertEqual(state["phase"], "empty_project")
        self.assertFalse(state["can_evaluate"])
        self.assertFalse(state["can_generate_report"])
        self.assertFalse(state["report_current"])

    def test_current_data_evaluation_report(self):
        state = self.state()
        self.assertTrue(state["evaluation_current"])
        self.assertTrue(state["report_current"])

    def test_failed_document_requires_action_not_endless_wait(self):
        for status in ("failed", "waiting_llm"):
            with self.subTest(status=status):
                state = self.state(docs=[{**self.docs[0], "status": status}])
                self.assertEqual(state["phase"], "documents_need_attention")
                self.assertIn("재시도", state["message"])
                self.assertFalse(state["can_evaluate"])
                self.assertFalse(state["can_generate_report"])

    def test_new_upload_requires_re_evaluation_and_retains_drafts(self):
        before = copy.deepcopy(self.sections)
        uploaded = self.docs + [{"id": "doc-2", "sha256": "second", "status": "queued", "updated_at": self.now}]
        self.assertEqual(self.state(docs=uploaded)["phase"], "processing_documents")
        uploaded[1]["status"] = "completed"
        state = self.state(docs=uploaded)
        self.assertEqual(state["phase"], "evaluation_required")
        self.assertFalse(state["can_generate_report"])
        self.assertEqual(self.sections, before)

    def test_optional_failure_and_cancellation_do_not_block_completed_documents(self):
        docs = self.docs + [{**self.docs[0], 'id':'failed','status':'failed'},
                            {**self.docs[0], 'id':'cancelled','status':'cancelled'}]
        snapshot = input_snapshot_from_rows(docs, self.run)
        run = {**self.run, 'input_snapshot':snapshot}
        state = evaluate_freshness(snapshot, run, [])
        self.assertTrue(state['can_evaluate'])
        self.assertTrue(state['can_generate_report'])
        self.assertEqual(state['pending_document_count'],0)
        self.assertEqual(state['excluded_document_count'],2)

    def test_failed_foundation_still_blocks_workflow(self):
        for role in ('project_plan','pdm'):
            docs = self.docs + [{**self.docs[0], 'id':'foundation','status':'failed','upload_role':role}]
            self.assertFalse(self.state(docs=docs)['can_evaluate'])

    def test_only_cancelled_documents_never_allow_evaluation(self):
        self.assertFalse(self.state(docs=[{**self.docs[0],'status':'cancelled'}])['can_evaluate'])

    def test_same_count_replacement_is_not_mistaken_for_current(self):
        replaced = [{**self.docs[0], "sha256": "replacement"}]
        self.assertFalse(self.state(docs=replaced)["evaluation_current"])

    def test_same_file_reanalysis_changes_revision(self):
        changed = [{**self.docs[0], "updated_at": self.now + timedelta(minutes=9)}]
        self.assertFalse(self.state(docs=changed)["evaluation_current"])

    def test_re_evaluation_marks_previous_report_stale(self):
        run = {**self.run, "id": "run-2", "completed_at": self.now + timedelta(minutes=9)}
        state = self.state(run=run)
        self.assertTrue(state["evaluation_current"])
        self.assertEqual(state["stale_section_ids"], ["summary-ko"])
        self.assertEqual(state["phase"], "report_required")

    def test_new_report_after_re_evaluation_is_current(self):
        run = {**self.run, "id": "run-2"}
        sections = [{**self.sections[0], "generation_metadata": {"input_snapshot": input_snapshot_from_rows(self.docs, run)}}]
        self.assertTrue(self.state(run=run, sections=sections)["report_current"])

    def test_fingerprint_independent_of_document_query_order(self):
        docs = self.docs + [{**self.docs[0], "id": "doc-2"}]
        self.assertEqual(input_snapshot_from_rows(docs), input_snapshot_from_rows(list(reversed(docs))))

    def test_legacy_evaluation_compares_start_not_completion(self):
        run = {**self.run, "input_snapshot": {}}
        self.assertTrue(self.state(run=run)["evaluation_current"])
        raced = [{**self.docs[0], "updated_at": self.now + timedelta(minutes=1, seconds=30)}]
        self.assertFalse(self.state(docs=raced, run=run)["evaluation_current"])

    def test_legacy_drafts_and_missing_drafts(self):
        sections = [{**self.sections[0], "generation_metadata": {}}]
        self.assertTrue(self.state(sections=sections)["report_current"])
        sections[0]["generated_at"] = self.now
        self.assertFalse(self.state(sections=sections)["report_current"])
        sections[0]["content"] = ""
        self.assertEqual(self.state(sections=sections)["missing_section_ids"], ["summary-ko"])

    def test_unknown_snapshot_never_matches(self):
        self.assertFalse(snapshots_match({}, {}))
        self.assertFalse(snapshots_match(None, self.snapshot))

    def test_running_reevaluation_prevents_old_result_being_exported_as_current(self):
        state = evaluate_freshness(self.snapshot, self.run, self.sections, active_evaluation=True)
        self.assertEqual(state["phase"], "evaluation_active")
        self.assertFalse(state["can_generate_report"])
        self.assertFalse(state["report_current"])

    def test_recovery_releases_only_generating_rows_without_erasing_content(self):
        conn = MagicMock()
        conn.execute.return_value.rowcount = 2
        self.assertEqual(recover_interrupted_sections(conn), 2)
        query = conn.execute.call_args.args[0]
        self.assertIn("WHERE status='generating'", query)
        self.assertIn("THEN 'draft' ELSE 'empty'", query)
        self.assertNotIn("content=", query)


if __name__ == "__main__":
    unittest.main()
