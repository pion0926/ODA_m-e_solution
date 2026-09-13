import unittest
import uuid
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from kodame_intake import admin, auth, db


class BootstrapSafetyTests(unittest.TestCase):
    def test_restart_never_resets_credentials_reactivates_or_seeds_demo_accounts(self):
        account, project = uuid.uuid4(), uuid.uuid4()
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{"id": account}, {"id": project}]
        with patch.object(db, "SEED_DEMO_ACCOUNTS", False), patch.object(db, "hash_password") as hasher:
            self.assertEqual(db._ensure_bootstrap(conn), (account, project))
        sql = "\n".join(call.args[0] for call in conn.execute.call_args_list)
        self.assertNotIn("password_hash=", sql)
        self.assertNotIn("is_active=true", sql)
        self.assertNotIn("INSERT INTO accounts", sql)
        hasher.assert_not_called()

    def test_first_start_only_creates_one_admin_and_empty_project(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [None, None]
        with patch.object(db, "SEED_DEMO_ACCOUNTS", False), patch.object(db, "hash_password", return_value="hash"):
            db._ensure_bootstrap(conn)
        sql = [call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(sum("INSERT INTO accounts" in q for q in sql), 1)
        self.assertEqual(sum("INSERT INTO projects" in q for q in sql), 1)
        self.assertFalse(any("intake_documents" in q or "report_sections" in q for q in sql))


class ServiceAccountTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = nullcontext()
        self.db_patch = patch.object(admin, "connection", return_value=nullcontext(self.conn))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def test_issued_account_is_empty_without_bootstrap_membership(self):
        with patch.object(admin, "hash_password", return_value="hashed-password"):
            result = admin.create_account("NewClient", "SafePassword123!", "새 사용자")
        self.assertEqual(result["email"], "newclient@kodame.local")
        self.assertIsNone(result["project"])
        self.assertFalse(result["is_admin"])
        self.assertNotIn("password", result)
        queries = [call.args[0] for call in self.conn.execute.call_args_list]
        self.assertEqual(len(queries), 1)
        self.assertNotIn("project_members", queries[0])

    def test_deactivation_immediately_revokes_sessions(self):
        self.conn.execute.return_value.fetchone.return_value = {"is_admin": False}
        admin.update_account_status(str(uuid.uuid4()), False)
        self.assertTrue(any("DELETE FROM auth_sessions" in call.args[0] for call in self.conn.execute.call_args_list))

    def test_issued_account_and_membership_are_saved_together(self):
        project_id = str(uuid.uuid4())
        self.conn.execute.return_value.fetchone.return_value = {"id": project_id, "name": "빈 고객 프로젝트", "default_locale": "ko"}
        with patch.object(admin, "hash_password", return_value="hash"):
            result = admin.create_account("atomic_user", "SafePassword123!", "고객", project_id=project_id)
        self.assertEqual(result["project"]["id"], project_id)
        self.conn.transaction.assert_called_once()
        queries = [call.args[0] for call in self.conn.execute.call_args_list]
        self.assertTrue(any("INSERT INTO accounts" in query for query in queries))
        self.assertTrue(any("INSERT INTO project_members" in query for query in queries))
        self.assertFalse(any("intake_documents" in query for query in queries))

    def test_unknown_project_does_not_create_an_orphan_account(self):
        self.conn.execute.return_value.fetchone.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            admin.create_account("no_project", "SafePassword123!", "고객", project_id=str(uuid.uuid4()))
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertFalse(any("INSERT INTO accounts" in call.args[0] for call in self.conn.execute.call_args_list))

    def test_admin_cannot_be_disabled_via_client_account_action(self):
        self.conn.execute.return_value.fetchone.return_value = {"is_admin": True}
        with self.assertRaises(HTTPException) as ctx:
            admin.update_account_status(str(uuid.uuid4()), False)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_password_reset_revokes_existing_sessions(self):
        self.conn.execute.return_value.fetchone.return_value = {"id": uuid.uuid4()}
        with patch.object(admin, "hash_password", return_value="new-hash"):
            result = admin.reset_account_password(str(uuid.uuid4()), "NewPassword123!")
        self.assertTrue(result["sessions_revoked"])
        self.assertTrue(any("DELETE FROM auth_sessions" in call.args[0] for call in self.conn.execute.call_args_list))

    def test_project_membership_removal_clears_only_that_selection(self):
        owner, target = uuid.uuid4(), uuid.uuid4()
        self.conn.execute.return_value.fetchone.side_effect = [{"owner_account_id": owner, "default_locale": "ko"}, {"id": target}]
        result = admin.assign_project_member(str(uuid.uuid4()), str(target), remove=True)
        self.assertFalse(result["assigned"])
        queries = [call.args[0] for call in self.conn.execute.call_args_list]
        self.assertTrue(any("selected_project_id=NULL" in q for q in queries))

    def test_mutating_apis_follow_individual_admin_menu_setting(self):
        for path, expected in [
            ("/api/v2/intake/uploads", "evidence_upload"),
            ("/api/v2/intake/jobs/document/retry", "evidence_upload"),
            ("/api/v2/evaluations", "evaluation_board"),
            ("/api/v2/pdm/refresh", "project_indicators"),
            ("/api/v2/report/generate-all", "evaluation_report"),
        ]:
            with self.subTest(path=path):
                self.assertEqual(admin.mutation_menu_permission("POST", path), expected)
                self.assertIsNone(admin.mutation_menu_permission("GET", path))


class ProjectSelectionTests(unittest.TestCase):
    def test_unauthorized_project_cannot_be_selected(self):
        conn = MagicMock()
        conn.transaction.return_value = nullcontext()
        conn.execute.return_value.fetchone.return_value = None
        with patch.object(auth, "connection", return_value=nullcontext(conn)):
            with self.assertRaises(HTTPException) as ctx:
                auth.select_project("token", str(uuid.uuid4()), str(uuid.uuid4()))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertFalse(any("UPDATE auth_sessions" in call.args[0] for call in conn.execute.call_args_list))

    def test_session_prefers_explicit_selection_not_project_update_time(self):
        conn = MagicMock()
        conn.transaction.return_value = nullcontext()
        conn.execute.return_value.fetchone.return_value = {"account_id": uuid.uuid4(), "project_id": uuid.uuid4()}
        with patch.object(auth, "connection", return_value=nullcontext(conn)):
            auth.load_session("token")
        query = conn.execute.call_args_list[0].args[0]
        self.assertIn("p.id=s.selected_project_id", query)
        self.assertNotIn("p.updated_at DESC", query)


if __name__ == "__main__":
    unittest.main()
