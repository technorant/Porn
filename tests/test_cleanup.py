import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from github_achievement.api import GitHubError
from github_achievement.cleanup import cleanup_record, cleanup_tracked, delete_merged_branch
from github_achievement.cli import build_parser, execute_run, main
from github_achievement.config import Config
from github_achievement.state import StateStore
from github_achievement.workflows import WorkflowRunner
from tests.test_workflows import FakeGitHub


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = StateStore(self.path / "progress.sqlite3")
        self.addCleanup(self.store.close)
        self.api = FakeGitHub()
        self.config = Config("alice/lab", "primary")
        self.runner = WorkflowRunner(self.config, self.api, sleep=lambda _: None)
        self.runner.preflight("pull-shark")
        self.id = self.store.start("alice", "alice/lab", "pull-shark")
        self.branch = f"achievement/pull-shark/{self.id}"
        self.api.branch = self.branch
        self.api.remote["merged"] = True
        self.store.finish(self.id, branch=self.branch, commit_sha="commit-sha", number=7, warning="Old cleanup error")

    def test_preview_checks_remote_state_without_deleting_or_editing_progress(self):
        before = self.store.history()
        result = cleanup_tracked(self.runner, self.store)
        self.assertEqual(result[0]["status"], "ready")
        self.assertTrue(all(method == "GET" for method, _, _ in self.api.calls))
        self.assertEqual(self.store.history(), before)

    def test_cleanup_is_idempotent_and_preserves_success_counts(self):
        result = cleanup_tracked(self.runner, self.store, execute=True)
        self.assertEqual(result[0]["status"], "deleted")
        self.assertEqual(self.store.count("alice", "alice/lab", "pull-shark"), 1)
        self.assertIsNone(self.store.history()[0]["detail"]["warning"])
        repeated = cleanup_tracked(self.runner, self.store, execute=True)
        self.assertEqual(repeated[0]["status"], "already_clean")
        self.assertEqual(sum(method == "DELETE" for method, _, _ in self.api.calls), 1)

    def test_unmerged_pr_is_kept(self):
        self.api.remote["merged"] = False
        self.assertEqual(cleanup_tracked(self.runner, self.store, execute=True)[0]["status"], "kept")
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))

    def test_branch_with_new_commits_is_kept(self):
        self.api.branch_sha = "new-work"
        result = cleanup_tracked(self.runner, self.store, execute=True)
        self.assertEqual(result[0]["status"], "kept")
        self.assertIn("changed", result[0]["reason"])
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))

    def test_default_unknown_and_backup_branches_never_deleted(self):
        for branch in ("main", "achievement-backup/old", "achievement/pull-shark/not-a-valid-id"):
            record = self.store.history()[0]
            record["detail"]["branch"] = branch
            self.assertEqual(cleanup_record(self.runner, record, execute=True)["status"], "kept")
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))

    def test_wrong_pr_branch_is_kept(self):
        self.api.branch = "different-branch"
        self.assertEqual(cleanup_tracked(self.runner, self.store, execute=True)[0]["status"], "kept")

    def test_other_accounts_and_repos_are_not_selected(self):
        for account, repo in (("bob", "alice/lab"), ("alice", "alice/elsewhere")):
            operation = self.store.start(account, repo, "pull-shark")
            self.store.finish(operation, branch="main")
        self.assertEqual(len(cleanup_tracked(self.runner, self.store)), 1)

    def test_automatic_deletion_race_422_is_already_clean(self):
        self.api.cleanup_error = GitHubError("Reference does not exist", 422)
        result = delete_merged_branch(self.api, "alice/lab", self.branch, "commit-sha")
        self.assertEqual(result["status"], "already_clean")

    def test_422_with_existing_branch_is_not_misreported_as_deleted(self):
        api = Mock()
        api.request.side_effect = [{"object": {"sha": "commit-sha"}}, GitHubError("Protected", 422), {"object": {"sha": "commit-sha"}}]
        with self.assertRaises(GitHubError):
            delete_merged_branch(api, "alice/lab", self.branch, "commit-sha")

    def test_rate_error_during_deletion_verification_is_not_hidden(self):
        api = Mock()
        api.request.side_effect = [{"object": {"sha": "commit-sha"}}, GitHubError("Reference changed", 422),
                                   GitHubError("Rate limited", 429, retry_after=600)]
        with self.assertRaises(GitHubError) as error:
            delete_merged_branch(api, "alice/lab", self.branch, "commit-sha")
        self.assertEqual(error.exception.retry_after, 600)

    def test_cleanup_stops_after_rate_error_and_records_it(self):
        self.api.cleanup_error = GitHubError("Rate limited", 429, retry_after=600)
        operation = self.store.start("alice", "alice/lab", "pull-shark")
        self.store.finish(operation, branch=f"achievement/pull-shark/{operation}", commit_sha="commit-sha", number=7)
        self.api.branch = f"achievement/pull-shark/{operation}"
        result = cleanup_tracked(self.runner, self.store, execute=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "error")
        self.assertEqual(self.store.count("alice", "alice/lab", "pull-shark"), 2)

    def test_empty_cleanup_needs_no_network_or_credentials(self):
        with patch.dict("os.environ", {}, clear=True), patch("github_achievement.cli.make_runner", side_effect=AssertionError("No network")), redirect_stdout(io.StringIO()):
            code = main(["cleanup", "--env-file", str(self.path / "absent.env"), "--state-dir", str(self.path / "empty")])
        self.assertEqual(code, 0)

    def test_rate_limited_cleanup_stops_next_workflow_operation(self):
        args = build_parser().parse_args(["run", "pull-shark", "--count", "2", "--execute", "--skip-badge-check"])
        runner = Mock()
        runner.preflight.return_value = {"account": "alice"}
        runner.run_one.return_value = {"url": "https://github.com/alice/lab/pull/7", "cleanup": {"rate_limited": True}}
        with patch("github_achievement.cli.make_runner", return_value=runner), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(GitHubError, "Stopping"):
                execute_run(args, self.config, self.path / "run")
        self.assertEqual(runner.run_one.call_count, 1)
