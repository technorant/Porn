import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from github_achievement.cli import main, run_wizard
from github_achievement.config import Config
from github_achievement.messages import (DEFAULT_MESSAGE_DIR, MESSAGE_FILES, PREVIEW_OPERATION,
                                         load_message_templates, render_messages, validate_message_templates)
from github_achievement.onboarding import save_config
from github_achievement.ui import Console


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(repo="alice/lab")

    def render(self, **overrides):
        return render_messages(replace(self.config, **overrides), "pull-shark", PREVIEW_OPERATION)

    def test_1024_operations_have_distinct_fields_for_solo_and_pair(self):
        custom = replace(self.config, **{field: "My {badge} activity in {repo}" for field in MESSAGE_FILES})
        for config in (self.config, custom):
            for workflow in ("pull-shark", "pair-extraordinaire"):
                with self.subTest(workflow=workflow, custom=config == custom):
                    templates = validate_message_templates(config, workflow)
                    rows = [render_messages(config, workflow, f"{index:032x}",
                                            coauthor=("Bob", "2+bob@users.noreply.github.com"),
                                            message_index=index, templates=templates)
                            for index in range(1024)]
                    for field in MESSAGE_FILES:
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

    def test_wizard_runs_without_asking_for_messages(self):
        original = self.env_file.read_text(encoding="utf-8")
        with patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", side_effect=["pair-extraordinaire", "base", "execute"]
        ), patch.object(Console, "ask", side_effect=AssertionError("Messages must come from files")), patch(
            "github_achievement.cli.main", return_value=0
        ) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(run_wizard(self.env_file, self.path / "state"), 0)
        command = execute.call_args.args[0]
        self.assertFalse(any(arg.startswith("--pr-title") for arg in command))
        self.assertIn("--execute", command)
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), original)

    def test_wizard_preview_shows_automatic_message_source(self):
        with patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", side_effect=["pull-shark", "base", "preview"]
        ), patch.object(Console, "ask", side_effect=AssertionError("No message prompts")), patch(
            "github_achievement.cli.make_runner", side_effect=AssertionError("No network")
        ), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run_wizard(self.env_file, self.path / "state"), 0)
        self.assertIn("Message files:", output.getvalue())
        self.assertIn("selected automatically", output.getvalue())
        self.assertFalse((self.path / "state").exists())


class MessageFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = Config(repo="alice/lab", messages_dir=self.directory)
        for filename in MESSAGE_FILES.values():
            (self.directory / filename).write_text(
                "# Ignored comment\n\nFirst {badge} record\nSecond {badge} record\n", encoding="utf-8-sig")

    def test_file_order_wraparound_and_multiline_descriptions(self):
        (self.directory / "prdescription.txt").write_text("First line\\nSecond line\n", encoding="utf-8")
        templates = validate_message_templates(self.config, "pull-shark")
        first = render_messages(self.config, "pull-shark", "a" * 32, templates=templates)
        second = render_messages(self.config, "pull-shark", "b" * 32, message_index=1, templates=templates)
        wrapped = render_messages(self.config, "pull-shark", "c" * 32, message_index=2, templates=templates)
        self.assertTrue(first["pr_title"].startswith("First Pull Shark record"))
        self.assertTrue(second["pr_title"].startswith("Second Pull Shark record"))
        self.assertTrue(wrapped["pr_title"].startswith("First Pull Shark record"))
        self.assertIn("First line\nSecond line", second["pr_body"])
        self.assertNotEqual(first["pr_title"], wrapped["pr_title"])

    def test_bundled_files_are_available_without_cwd_lookup(self):
        self.assertEqual(set(path.name for path in DEFAULT_MESSAGE_DIR.glob("*.txt")), set(MESSAGE_FILES.values()))
        for workflow in ("pull-shark", "pair-extraordinaire", "yolo"):
            templates = validate_message_templates(Config(repo="alice/lab"), workflow)
            self.assertTrue(all(len(entries) == 12 for entries in templates.values()))

    def test_missing_empty_and_wrong_encoding_files_have_actionable_errors(self):
        path = self.directory / "prtitle.txt"
        for contents, error in ((None, "Cannot read message file"), (b"# no messages\n", "at least one"),
                                (b"\xff\xfe", "UTF-8")):
            with self.subTest(error=error):
                if contents is None:
                    path.unlink()
                else:
                    path.write_bytes(contents)
                with self.assertRaisesRegex(ValueError, error):
                    validate_message_templates(self.config, "pull-shark")

    def test_bad_later_entry_is_rejected_before_it_can_be_selected(self):
        (self.directory / "mergedescription.txt").write_text("Valid\nInvalid {unknown}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mergedescription.txt, entry 2"):
            render_messages(self.config, "pull-shark", PREVIEW_OPERATION)

    def test_file_snapshot_is_stable_until_next_run(self):
        templates = validate_message_templates(self.config, "pull-shark")
        (self.directory / "prtitle.txt").write_text("Changed title\n", encoding="utf-8")
        current = render_messages(self.config, "pull-shark", PREVIEW_OPERATION, templates=templates)
        later = render_messages(self.config, "pull-shark", PREVIEW_OPERATION)
        self.assertTrue(current["pr_title"].startswith("First Pull Shark record"))
        self.assertTrue(later["pr_title"].startswith("Changed title"))

    def test_directory_setting_is_relative_to_env_file(self):
        env_file = self.directory / ".env"
        env_file.write_text("TARGET_REPO=alice/lab\nMESSAGES_DIR=custom-text\n", encoding="utf-8")
        config = Config.load(env_file, {})
        self.assertEqual(config.messages_dir, self.directory / "custom-text")
        shell_config = Config.load(env_file, {"MESSAGES_DIR": str(DEFAULT_MESSAGE_DIR)})
        self.assertEqual(shell_config.messages_dir, DEFAULT_MESSAGE_DIR)

    def test_single_override_only_replaces_its_own_file(self):
        templates = load_message_templates(replace(self.config, pr_title="My title"))
        self.assertEqual(templates["pr_title"], ("My title",))
        self.assertEqual(len(templates["commit_message"]), 2)


if __name__ == "__main__":
    unittest.main()
