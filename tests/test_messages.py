import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from github_achievement.cli import main, run_wizard
from github_achievement.config import Config
from github_achievement.messages import MESSAGE_DEFAULTS, PREVIEW_OPERATION, render_messages
from github_achievement.onboarding import save_config
from github_achievement.ui import Console


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(repo="alice/lab")

    def render(self, **overrides):
        return render_messages(replace(self.config, **overrides), "pull-shark", PREVIEW_OPERATION)

    def test_1024_operations_have_distinct_fields_for_solo_and_pair(self):
        custom = replace(self.config, **{field: "My {badge} activity in {repo}" for field in MESSAGE_DEFAULTS})
        for config in (self.config, custom):
            for workflow in ("pull-shark", "pair-extraordinaire"):
                with self.subTest(workflow=workflow, custom=config == custom):
                    rows = [render_messages(config, workflow, f"{index:032x}",
                                            coauthor=("Bob", "2+bob@users.noreply.github.com"))
                            for index in range(1024)]
                    for field in MESSAGE_DEFAULTS:
                        self.assertEqual(len({row[field] for row in rows}), 1024, field)
                    if workflow == "pair-extraordinaire":
                        self.assertTrue(all(row["commit_message"].endswith(
                            "Co-authored-by: Bob <2+bob@users.noreply.github.com>") for row in rows))

    def test_multiline_templates_literal_braces_and_disclosure(self):
        messages = self.render(pr_body="File: {path}\\n\\nDetails: {{record}} in {repo}",
                               commit_message="Update record\n\nKeep operation details")
        self.assertIn("File: .github-achievements/pull-shark.json\n\nDetails: {record} in alice/lab", messages["pr_body"])
        self.assertIn("Update record\n\nKeep operation details", messages["commit_message"])
        self.assertIn("Automated workflow", messages["pr_body"])
        self.assertIn("Automated workflow", messages["merge_message"])

    def test_templates_are_literal_and_cannot_access_attributes_or_format_specs(self):
        for template in ("{token}", "{repo.upper}", "{repo[0]}", "{repo!r}", "{repo:>20}", "{}", "{"):
            with self.subTest(template=template), self.assertRaisesRegex(ValueError, "PR_TITLE"):
                self.render(pr_title=template)
        messages = self.render(pr_title="$(literal) `text` {repo}")
        self.assertTrue(messages["pr_title"].startswith("$(literal) `text` alice/lab"))

    def test_limits_count_utf8_bytes_and_generated_metadata(self):
        suffix_size = len(f" [{PREVIEW_OPERATION}]".encode())
        self.assertEqual(len(self.render(pr_title="x" * (256 - suffix_size))["pr_title"].encode()), 256)
        for field, value in (("pr_title", "x" * (257 - suffix_size)), ("merge_title", "é" * 130),
                             ("pr_body", "x" * 65536), ("commit_message", "x" * 65536),
                             ("merge_message", "x" * 65536)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "exceeds"):
                self.render(**{field: value})

    def test_blank_titles_multiline_titles_and_control_characters_are_rejected(self):
        for field, value in (("pr_title", "  "), ("pr_title", "line\\nline"), ("merge_title", "line\nline"),
                             ("pr_body", "text\x00"), ("commit_message", "text\x1b")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.render(**{field: value})
        self.assertIn("Record Pull Shark activity", self.render(pr_title="")["pr_title"])

    def test_custom_trailers_cannot_override_verified_helper_identity(self):
        for field in ("commit_message", "merge_title", "merge_message"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "added automatically"):
                self.render(**{field: "Co-authored-by: Other <other@example.com>"})


class MessageCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.env_file = self.path / ".env"
        self.env_file.write_text("TARGET_REPO=alice/lab\nPR_TITLE=Saved {badge} record\n"
                                 "PR_BODY=First line\\nSecond line\n", encoding="utf-8")
        self.environment = patch.dict("os.environ", {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def invoke(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error), patch(
            "github_achievement.cli.make_runner", side_effect=AssertionError("Offline test: no GitHub calls")
        ):
            code = main(["--env-file", str(self.env_file), "--state-dir", str(self.path / "state"), *args])
        return code, output.getvalue(), error.getvalue()

    def test_env_shell_cli_precedence_and_preview_has_no_writes(self):
        config = Config.load(self.env_file, {"PR_TITLE": "Shell {badge} record"})
        self.assertEqual(config.pr_title, "Shell {badge} record")
        self.assertEqual(config.pr_body, "First line\\nSecond line")
        with patch.dict("os.environ", {"PR_TITLE": "Shell {badge} record"}):
            code, output, error = self.invoke("run", "pull-shark", "--pr-title", "Command {badge} record",
                                              "--merge-message", "Custom merge for {repo}")
        self.assertEqual(code, 0, error)
        self.assertIn("Command Pull Shark record", output)
        self.assertIn("Custom merge for alice/lab", output)
        self.assertNotIn("Shell Pull Shark", output)
        self.assertIn("First line", output)
        self.assertNotIn("First line\\nSecond line", output)
        self.assertFalse((self.path / "state").exists())

    def test_invalid_template_stops_before_credential_setup(self):
        with patch("github_achievement.cli.ensure_credentials", side_effect=AssertionError("No setup")):
            code, _, error = self.invoke("run", "pull-shark", "--execute", "--merge-title", "Invalid {token}")
        self.assertEqual(code, 1)
        self.assertIn("MERGE_TITLE", error)

    def test_message_options_need_an_explicit_pr_workflow(self):
        for args in (("run", "--pr-title", "Title"), ("run", "quickdraw", "--pr-title", "Title"),
                     ("run", "galaxy-brain", "--merge-title", "Title")):
            with self.subTest(args=args):
                code, _, _ = self.invoke(*args)
                self.assertEqual(code, 1)

    def test_shared_env_templates_do_not_change_other_badges(self):
        code, output, error = self.invoke("run", "quickdraw")
        self.assertEqual(code, 0, error)
        self.assertNotIn("Message preview", output)

    def test_credential_update_preserves_existing_message_templates(self):
        config = Config.load(self.env_file, {})
        save_config(replace(config, token="primary-secret", helper_token="helper-secret"), self.env_file)
        loaded = Config.load(self.env_file, {})
        self.assertEqual(loaded.pr_title, config.pr_title)
        self.assertEqual(loaded.pr_body, config.pr_body)

    def test_wizard_customization_reaches_command_without_saving_env(self):
        original = self.env_file.read_text(encoding="utf-8")
        with patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", side_effect=["pair-extraordinaire", "base", "messages", "execute"]
        ), patch.object(Console, "ask", side_effect=["My title", "My description", "My commit", "My merge", "Merge details"]), patch(
            "github_achievement.cli.main", return_value=0
        ) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(run_wizard(self.env_file, self.path / "state"), 0)
        command = execute.call_args.args[0]
        self.assertIn("--pr-title=My title", command)
        self.assertIn("--merge-message=Merge details", command)
        self.assertIn("--execute", command)
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), original)

    def test_wizard_invalid_edit_returns_to_preview_without_applying_it(self):
        with patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", side_effect=["pull-shark", "base", "messages", "preview"]
        ), patch.object(Console, "ask", side_effect=["{invalid}", "Body", "Commit", "Merge", "Details"]), patch(
            "github_achievement.cli.make_runner", side_effect=AssertionError("No network")
        ), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run_wizard(self.env_file, self.path / "state"), 0)
        self.assertIn("Edits were not applied", output.getvalue())
        self.assertFalse((self.path / "state").exists())


if __name__ == "__main__":
    unittest.main()
