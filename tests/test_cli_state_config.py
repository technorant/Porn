import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from github_achievement.catalog import target_for
from github_achievement.cli import build_parser, main
from github_achievement.config import Config, read_env, validate_repo
from github_achievement.state import RunLock, StateStore
from github_achievement.workflows import WorkflowRunner
from tests.test_workflows import FakeGitHub


class ConfigTests(unittest.TestCase):
    def test_env_file_is_literal_and_environment_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# test\nexport GITHUB_TOKEN=file-secret\nTARGET_REPO=alice/lab\nCOAUTHOR_NAME='Bob Smith'\nEXAMPLE=$(do-not-run)\n", encoding="utf-8")
            config = Config.load(path, {"GH_TOKEN": "shell-secret"})
            self.assertEqual(config.token, "shell-secret")
            self.assertEqual(config.coauthor_name, "Bob Smith")
            self.assertEqual(read_env(path)["EXAMPLE"], "$(do-not-run)")
            self.assertNotIn("shell-secret", repr(config))

    def test_invalid_env_does_not_echo_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("GITHUB_TOKEN='secret\n", encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                read_env(path)
            self.assertNotIn("secret", str(error.exception))

    def test_repo_validation_blocks_url_and_path_injection(self):
        for repo in ("alice/..", "alice/a/b", "https://github.com/alice/lab", "alice/lab?x=1", "alice/lab#frag", "../repo"):
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                validate_repo(repo)
        self.assertEqual(validate_repo("alice/lab.py"), "alice/lab.py")

    def test_coauthor_cannot_inject_commit_trailers(self):
        config = Config("alice/lab", "token", "helper", coauthor_name="Bob\nFake: trailer", coauthor_email="bob@example.com")
        with self.assertRaises(ValueError):
            config.validate("pair-extraordinaire", credentials=True)

    def test_single_tier_achievement_rejects_gold(self):
        with self.assertRaisesRegex(ValueError, "base tier"):
            target_for("quickdraw", "gold")


class StateTests(unittest.TestCase):
    def test_scope_persistence_and_incomplete_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            with StateStore(path) as store:
                operation = store.start("Alice", "Alice/Lab", "pull-shark")
                store.checkpoint(operation, url="https://github.com/alice/lab/pull/1")
                store.finish(operation)
                store.start("alice", "alice/lab", "pull-shark")
                failed = store.start("alice", "alice/lab", "pull-shark")
                store.finish(failed, "failed", error="API failure")
            with StateStore(path) as store:
                self.assertEqual(store.count("ALICE", "ALICE/LAB", "pull-shark"), 1)
                self.assertEqual(store.count("bob", "alice/lab", "pull-shark"), 0)
                self.assertEqual(store.count("alice", "alice/other", "pull-shark"), 0)
                self.assertEqual({r["status"] for r in store.history()}, {"completed", "running", "failed"})
                completed = next(r for r in store.history() if r["status"] == "completed")
                self.assertIn("url", completed["detail"])

    def test_run_lock_excludes_another_writer_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with RunLock(path):
                with self.assertRaisesRegex(ValueError, "Another run"):
                    with RunLock(path):
                        self.fail("Second lock should not be acquired")
            with RunLock(path):
                pass


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.environment = patch.dict("os.environ", {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.badges = patch("github_achievement.cli.check_badges", return_value={
            "account": "alice", "profile_url": "https://github.com/alice?tab=achievements",
            "badges": {"quickdraw": "not_visible"}, "note": "Not visible yet.",
        })
        self.badges.start()
        self.addCleanup(self.badges.stop)

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--env-file", str(self.path / ".env"), "--state-dir", str(self.path / "state"), *args])
        return code, output.getvalue(), errors.getvalue()

    def test_list_json_without_config_or_network(self):
        code, output, _ = self.invoke("list", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output)), 5)

    def test_default_preview_never_constructs_client_or_state(self):
        with patch("github_achievement.cli.make_runner", side_effect=AssertionError("No network allowed")):
            code, output, _ = self.invoke("run", "pull-shark", "--repo", "alice/lab", "--tier", "base")
        self.assertEqual(code, 0)
        self.assertIn("Preview only", output)
        self.assertFalse((self.path / "state").exists())

    def test_missing_token_stops_before_network(self):
        with patch("github_achievement.cli.make_runner", side_effect=AssertionError("No network allowed")):
            code, _, error = self.invoke("run", "quickdraw", "--repo", "alice/lab", "--execute")
        self.assertEqual(code, 1)
        self.assertIn("Set GITHUB_TOKEN", error)

    def test_dry_run_without_achievement_cannot_enter_setup_or_execute(self):
        with patch("github_achievement.cli.run_wizard", side_effect=AssertionError("Must not enter interactive setup")):
            code, _, error = self.invoke("run", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("Specify an achievement ID", error)

    def test_offline_status_does_not_create_empty_database(self):
        code, output, _ = self.invoke("status", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {"summary": [], "history": []})
        self.assertFalse((self.path / "state").exists())

    def test_tier_resume_uses_authenticated_account_and_does_not_repeat_success(self):
        primary = FakeGitHub()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), patch(
            "github_achievement.cli.make_runner", side_effect=lambda config: WorkflowRunner(config, primary)
        ):
            first = self.invoke("run", "quickdraw", "--repo", "alice/lab", "--tier", "base", "--execute")
            second = self.invoke("run", "quickdraw", "--repo", "alice/lab", "--tier", "base", "--execute")
        self.assertEqual(first[0], 0, first[2])
        self.assertEqual(second[0], 0, second[2])
        self.assertIn("0 operation(s) to run", second[1])
        self.assertEqual(sum(m == "POST" and p.endswith("/issues") for m, p, _ in primary.calls), 1)

    def test_doctor_is_read_only(self):
        primary = FakeGitHub()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), patch(
            "github_achievement.cli.make_runner", side_effect=lambda config: WorkflowRunner(config, primary)
        ):
            code, output, error = self.invoke("doctor", "--repo", "alice/lab", "--workflow", "pull-shark", "--json")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["account"], "alice")
        self.assertTrue(all(m == "GET" for m, _, _ in primary.calls))

    def test_common_options_work_before_and_after_command(self):
        for argv in (["--repo", "alice/lab", "list"], ["list", "--repo", "alice/lab"]):
            self.assertEqual(build_parser().parse_args(argv).repo, "alice/lab")

    def test_invalid_count_interval_and_conflicting_modes(self):
        for extra in (["--count", "0"], ["--interval", "nan"], ["--interval", "-1"],
                      ["--count", "1", "--tier", "base"], ["--execute", "--dry-run"]):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                build_parser().parse_args(["run", "pull-shark", *extra])
            self.assertEqual(error.exception.code, 2)

    def test_reset_without_expected_head_never_writes(self):
        primary = FakeGitHub()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}), patch(
            "github_achievement.cli.make_runner", side_effect=lambda config: WorkflowRunner(config, primary)
        ):
            code, _, error = self.invoke("reset-history", "--repo", "alice/lab", "--execute")
        self.assertEqual(code, 1)
        self.assertIn("--expected-head", error)
        self.assertTrue(all(m == "GET" for m, _, _ in primary.calls))


if __name__ == "__main__":
    unittest.main()
