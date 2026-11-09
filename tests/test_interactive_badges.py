import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from github_achievement.badges import check_badges, fetch_profile
from github_achievement.cli import main, run_wizard
from github_achievement.config import Config
from github_achievement.onboarding import create_repository, ensure_credentials, helper_credentials, save_config, setup
from github_achievement.ui import Choice, Console, clean
from tests.test_api import FakeOpener


def profile(slug="pair-extraordinaire", account="alice", *, markdown=False):
    body = f'''<a href="/{account}?achievement={slug}&amp;tab=achievements">
      <img src="https://github.githubassets.com/images/modules/profile/achievements/{slug}-default.png" />
    </a>'''
    if markdown:
        body = '<article class="markdown-body">' + body + '</article>'
    return f'<meta name="octolytics-dimension-user_login" content="{account}">' + body


class BadgeTests(unittest.TestCase):
    def test_badge_confirmation_uses_profile_elements(self):
        result = check_badges("alice", ["pair-extraordinaire", "quickdraw"], fetch=lambda _: profile())
        self.assertEqual(result["badges"], {"pair-extraordinaire": "visible", "quickdraw": "not_visible"})

    def test_readme_badge_link_cannot_prove_badge_award(self):
        result = check_badges("alice", ["pair-extraordinaire"], fetch=lambda _: profile(markdown=True))
        self.assertEqual(result["badges"]["pair-extraordinaire"], "not_visible")

    def test_unrecognized_and_login_pages_are_unknown(self):
        for page in ("<html>Sign in</html>", profile(account="someone-else")):
            result = check_badges("alice", ["pair-extraordinaire"], fetch=lambda _: page)
            self.assertEqual(result["badges"]["pair-extraordinaire"], "unknown")

    def test_arbitrary_image_host_cannot_prove_award(self):
        page = profile().replace("github.githubassets.com", "example.com")
        result = check_badges("alice", ["pair-extraordinaire"], fetch=lambda _: page)
        self.assertEqual(result["badges"]["pair-extraordinaire"], "not_visible")

    def test_fingerprinted_github_badge_assets(self):
        page = profile().replace("/images/modules/profile/achievements/pair-extraordinaire-default.png", "/assets/pair-extraordinaire-default-a1b2c3.png")
        result = check_badges("alice", ["pair-extraordinaire"], fetch=lambda _: page)
        self.assertEqual(result["badges"]["pair-extraordinaire"], "visible")

    def test_failed_profile_request_is_unknown(self):
        def offline(_):
            raise URLError("offline")
        result = check_badges("alice", ["quickdraw"], fetch=offline)
        self.assertEqual(result["badges"]["quickdraw"], "unknown")

    def test_polling_waits_for_visibility_without_writes(self):
        now, sleeps, pages = [0], [], [profile("quickdraw"), profile()]
        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds
        result = check_badges("alice", ["pair-extraordinaire"], wait=30, fetch=lambda _: pages.pop(0),
                              sleep=sleep, clock=lambda: now[0])
        self.assertEqual(result["badges"]["pair-extraordinaire"], "visible")
        self.assertEqual(sleeps, [15])

    def test_polling_is_bounded_when_badge_is_hidden(self):
        now = [0]
        def sleep(seconds):
            now[0] += seconds
        result = check_badges("alice", ["pair-extraordinaire"], wait=20, fetch=lambda _: profile("quickdraw"),
                              sleep=sleep, clock=lambda: now[0])
        self.assertEqual(now[0], 20)
        self.assertEqual(result["badges"]["pair-extraordinaire"], "not_visible")

    def test_profile_fetch_never_sends_credentials(self):
        opener = FakeOpener(profile().encode())
        fetch_profile("alice", opener=opener)
        request = opener.requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("Cookie"))

    def test_username_and_wait_validation(self):
        for account in ("alice?tab=repositories", "../alice", "https://github.com/alice"):
            with self.assertRaises(ValueError):
                check_badges(account, fetch=lambda _: self.fail("Should not fetch"))
        with self.assertRaises(ValueError):
            check_badges("alice", wait=601)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"
        self.output = io.StringIO()
        redirect = redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.config = Config("alice/lab", "primary-secret")

    def test_pair_requests_helper_only_and_saves_it_without_printing(self):
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="helper-secret") as prompt:
            result = ensure_credentials(self.config, self.path, "pair-extraordinaire")
        prompt.assert_called_once()
        self.assertIn("Helper token", prompt.call_args.args[0])
        self.assertEqual(result.helper_token, "helper-secret")
        self.assertEqual(Config.load(self.path, {}).helper_token, "helper-secret")
        self.assertNotIn("helper-secret", self.output.getvalue())
        self.assertNotIn("primary-secret", self.output.getvalue())

    def test_solo_workflows_do_not_request_helper(self):
        for workflow in ("pull-shark", "quickdraw"):
            with patch("getpass.getpass", side_effect=AssertionError("Unexpected helper prompt")):
                result = helper_credentials(self.config, workflow, Console())
            self.assertEqual(result, self.config)

    def test_existing_helper_is_reused(self):
        config = Config("alice/lab", "primary", "helper")
        with patch("getpass.getpass", side_effect=AssertionError("No repeated prompt")):
            self.assertEqual(helper_credentials(config, "pair-extraordinaire", Console()), config)

    def test_helper_can_be_replaced_from_settings(self):
        config = Config("alice/lab", "primary", "old-helper")
        with patch("getpass.getpass", return_value="new-helper"):
            result = helper_credentials(config, "pair-extraordinaire", Console(), edit=True)
        self.assertEqual(result.helper_token, "new-helper")

    def test_noninteractive_pair_requires_helper_and_never_prompts(self):
        with patch("sys.stdin.isatty", return_value=False), patch("getpass.getpass", side_effect=AssertionError("No prompt")):
            with self.assertRaisesRegex(ValueError, "HELPER_TOKEN"):
                ensure_credentials(self.config, self.path, "pair-extraordinaire")

    def test_basic_setup_does_not_request_optional_helper(self):
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="primary" ) as prompt, patch.object(
            Console, "choose", return_value="existing"
        ), patch.object(Console, "ask", return_value="alice/lab"):
            result = setup(Config(), self.path)
        self.assertEqual(prompt.call_count, 1)
        self.assertEqual(result.repo, "alice/lab")
        self.assertEqual(result.helper_token, "")

    def test_read_only_connection_setup_cannot_create_repository(self):
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="primary"), patch.object(
            Console, "ask", return_value="alice/lab"
        ), patch("github_achievement.onboarding.setup", side_effect=AssertionError("Creation wizard must not run")):
            config = ensure_credentials(Config(), self.path, allow_create=False)
        self.assertEqual(config.repo, "alice/lab")
        self.assertEqual(config.token, "primary")

    def test_repository_creation_initializes_files_and_selected_visibility(self):
        with patch("github_achievement.onboarding.GitHubClient") as client, patch.object(Console, "ask", return_value="new-lab"), patch.object(
            Console, "choose", side_effect=["private", "create"]
        ):
            client.return_value.request.side_effect = [{"login": "alice"}, {
                "full_name": "alice/new-lab", "html_url": "https://github.com/alice/new-lab"}]
            result = create_repository("primary-secret", Console())
        self.assertEqual(result, "alice/new-lab")
        method, path, payload = client.return_value.request.call_args.args
        self.assertEqual((method, path), ("POST", "/user/repos"))
        self.assertTrue(payload["private"])
        self.assertTrue(payload["auto_init"])

    def test_cancel_repository_creation_does_not_write(self):
        with patch("github_achievement.onboarding.GitHubClient") as client, patch.object(Console, "ask", return_value="lab"), patch.object(
            Console, "choose", side_effect=["public", "back"]
        ):
            client.return_value.request.return_value = {"login": "alice"}
            with self.assertRaisesRegex(ValueError, "cancelled"):
                create_repository("primary", Console())
        self.assertEqual(client.return_value.request.call_count, 1)

    def test_config_save_failure_preserves_existing_file(self):
        self.path.write_text("TARGET_REPO=alice/old\n", encoding="utf-8")
        with patch("os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                save_config(self.config, self.path)
        self.assertEqual(self.path.read_text(), "TARGET_REPO=alice/old\n")
        self.assertEqual(list(self.path.parent.glob(".achievement-config-*")), [])

    def test_pair_preview_in_wizard_does_not_prompt_or_make_requests(self):
        save_config(self.config, self.path)
        with patch("os.environ", {}), patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", side_effect=["pair-extraordinaire", "base", "preview"]
        ), patch("getpass.getpass", side_effect=AssertionError("No secrets needed for preview")), patch(
            "github_achievement.cli.make_runner", side_effect=AssertionError("No API calls in preview")
        ):
            self.assertEqual(run_wizard(self.path, self.path.parent / "state"), 0)


class MenuTests(unittest.TestCase):
    def test_keyboard_navigation_returns_choice_and_restores_cursor(self):
        console = Console()
        console.terminal, console.color = True, False
        output = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), patch("github_achievement.ui.read_key", side_effect=["down", "enter"]), redirect_stdout(output):
            result = console.choose("Choose", [Choice("a", "One"), Choice("b", "Two")])
        self.assertEqual(result, "b")
        self.assertTrue(output.getvalue().endswith("\033[?25h"))

    def test_interrupt_restores_cursor(self):
        console = Console()
        console.terminal = True
        output = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), patch("github_achievement.ui.read_key", side_effect=KeyboardInterrupt), redirect_stdout(output):
            with self.assertRaises(KeyboardInterrupt):
                console.choose("Choose", [Choice("a", "One")])
        self.assertTrue(output.getvalue().endswith("\033[?25h"))

    def test_plain_menu_reprompts_on_invalid_choice(self):
        console = Console()
        console.terminal = False
        with patch("builtins.input", side_effect=["bad", "9", "2"]), redirect_stdout(io.StringIO()):
            self.assertEqual(console.choose("Choose", [Choice("a", "One"), Choice("b", "Two")]), "b")

    def test_no_color_and_remote_control_sequences(self):
        with patch.dict("os.environ", {"NO_COLOR": "1"}), patch("github_achievement.ui.enable_terminal", return_value=True):
            self.assertEqual(Console().paint("test", "cyan"), "test")
        self.assertEqual(clean("name\033[2J\r\nnext"), "name  next")

    def test_verify_json_is_clean_and_pending_is_exit_three(self):
        report = {"account": "alice", "badges": {"quickdraw": "not_visible"}, "note": "pending"}
        output = io.StringIO()
        with patch("github_achievement.cli.check_badges", return_value=report), redirect_stdout(output):
            code = main(["verify", "--account", "alice", "--achievement", "quickdraw", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output.getvalue()), report)


if __name__ == "__main__":
    unittest.main()
