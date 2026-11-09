import base64
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from github_achievement.api import GitHubError
from github_achievement.config import Config
from github_achievement.messages import render_messages
from github_achievement.state import StateStore
from github_achievement.workflows import WorkflowRunner


REPO = "/repos/alice/lab"


class FakeGitHub:
    def __init__(self, login="alice", user_id=1):
        self.user = {"id": user_id, "login": login}
        self.repo = {"owner": {"login": "alice"}, "full_name": "alice/lab", "permissions": {"push": True},
                     "default_branch": "release/main", "has_issues": True, "has_discussions": True,
                     "allow_merge_commit": True}
        self.calls = []
        self.merge_result = {"merged": True, "sha": "merge-sha"}
        self.merge_error = None
        self.cleanup_error = None
        self.content_sha = None
        self.heads = ["base-sha"]
        self.close_time = "2026-01-01T00:00:08Z"
        self.category_pages = []
        self.remote = {"merged": False, "merged_by": None}
        self.mergeability = [True]
        self.reviews = []
        self.author_logins = ["alice", "bob"]
        self.accepted_author = "alice"
        self.branch_deleted = False
        self.branch_sha = "commit-sha"
        self.branch = ""

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/user":
            return self.user
        if method == "GET" and path == "/user/emails":
            return [{"email": f"{self.user['login']}@example.com", "verified": True}]
        if method == "GET" and path == REPO:
            return self.repo
        if method == "GET" and "/git/ref/heads/" in path:
            if "achievement%2F" in path:
                if self.branch_deleted:
                    raise GitHubError("Reference does not exist", 404)
                return {"object": {"sha": self.branch_sha}}
            head = self.heads.pop(0) if len(self.heads) > 1 else self.heads[0]
            return {"object": {"sha": head}}
        if method == "GET" and "/contents/" in path:
            if self.content_sha:
                return {"sha": self.content_sha}
            raise GitHubError("Not found", 404)
        if method == "POST" and path.endswith("/git/refs"):
            self.branch = payload["ref"].removeprefix("refs/heads/")
            self.branch_deleted = False
            return {}
        if method == "PUT" and "/contents/" in path:
            return {"commit": {"sha": "commit-sha"}}
        if method == "POST" and path.endswith("/pulls"):
            return {"number": 7, "html_url": "https://github.com/alice/lab/pull/7"}
        if method == "GET" and path.endswith("/pulls/7"):
            mergeable = self.mergeability.pop(0) if len(self.mergeability) > 1 else self.mergeability[0]
            return {"number": 7, "head": {"sha": "commit-sha", "ref": self.branch, "repo": {"full_name": "alice/lab"}},
                    "user": {"login": "alice"}, "state": "closed" if self.remote["merged"] else "open",
                    "merged": self.remote["merged"], "mergeable": mergeable, "merged_by": self.remote["merged_by"]}
        if method == "GET" and "/reviews?" in path:
            return self.reviews
        if method == "PUT" and path.endswith("/merge"):
            if self.merge_error:
                raise self.merge_error
            self.remote.update(merged=self.merge_result.get("merged", False), merged_by=self.user)
            return self.merge_result
        if method == "DELETE":
            if self.cleanup_error:
                if self.cleanup_error.status in {404, 422}:
                    self.branch_deleted = True
                raise self.cleanup_error
            self.branch_deleted = True
            return {}
        if method == "POST" and path.endswith("/issues"):
            return {"number": 8, "html_url": "https://github.com/alice/lab/issues/8", "created_at": "2026-01-01T00:00:00Z"}
        if method in {"PATCH", "GET"} and path.endswith("/issues/8"):
            return {"state": "closed", "closed_at": self.close_time}
        if method == "GET" and "/git/commits/" in path:
            return {"tree": {"sha": "original-tree"}}
        if method == "POST" and path.endswith("/git/commits"):
            return {"sha": "new-root"}
        if method == "PATCH" and "/git/refs/heads/" in path:
            return {}
        raise AssertionError(f"Unexpected request: {method} {path}")

    def graphql(self, query, variables, *, mutation=False):
        self.calls.append(("GRAPHQL", query, variables))
        if "query CommitAuthors" in query:
            self.assert_query(mutation)
            return {"repository": {"object": {"authors": {"nodes": [{"user": {"login": login}} for login in self.author_logins]}}}}
        if "query VerifyAnswer" in query:
            self.assert_query(mutation)
            return {"node": {"isAnswered": True, "answer": {"id": "comment-id", "author": {"login": self.accepted_author}}}}
        if "query Categories" in query:
            self.assert_query(mutation)
            if self.category_pages:
                return self.category_pages.pop(0)
            return {"repository": {"id": "repo-id", "discussionCategories": {
                "nodes": [{"id": "category-id", "name": "Q&A", "isAnswerable": True}],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        if not mutation:
            raise AssertionError("Mutation was incorrectly marked read-only")
        if "mutation CreateQuestion" in query:
            return {"createDiscussion": {"discussion": {"id": "discussion-id", "url": "https://github.com/alice/lab/discussions/9"}}}
        if "mutation AddAnswer" in query:
            return {"addDiscussionComment": {"comment": {"id": "comment-id", "url": "https://github.com/alice/lab/discussions/9#comment"}}}
        if "mutation AcceptAnswer" in query:
            return {"markDiscussionCommentAsAnswer": {"discussion": {"id": "discussion-id", "isAnswered": True, "answer": {"id": "comment-id"}}}}
        raise AssertionError("Unexpected GraphQL operation")

    @staticmethod
    def assert_query(mutation):
        if mutation:
            raise AssertionError("Query incorrectly marked as a mutation")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name) / "progress.sqlite3")
        self.addCleanup(self.store.close)
        self.config = Config("alice/lab", "secret-primary", "secret-helper", "Bob", "bob@example.com")
        self.primary = FakeGitHub()
        self.helper = FakeGitHub("bob", 2)
        self.helper.remote = self.primary.remote
        self.sleeps = []
        self.runner = WorkflowRunner(self.config, self.primary, self.helper, sleep=self.sleeps.append)

    def execute(self, workflow):
        self.runner.preflight(workflow)
        return self.runner.run_one(workflow, self.store)

    def test_pull_request_uses_default_branch_and_merge_head_guard(self):
        result = self.execute("pull-shark")
        self.assertIn("/pull/7", result["url"])
        pr = next(p for m, path, p in self.primary.calls if m == "POST" and path.endswith("/pulls"))
        self.assertEqual(pr["base"], "release/main")
        merge = next(p for m, path, p in self.primary.calls if path.endswith("/merge"))
        self.assertEqual(merge["sha"], "commit-sha")
        self.assertEqual(merge["merge_method"], "merge")
        self.assertIn("Merge Pull Shark activity record", merge["commit_title"])
        self.assertIn("Operation:", merge["commit_message"])
        self.assertEqual(self.store.count("alice", "alice/lab", "pull-shark"), 1)
        self.assertTrue(any("release%2Fmain" in path for _, path, _ in self.primary.calls))

    def test_existing_activity_file_sha_and_coauthor_trailer(self):
        self.primary.content_sha = "old-content-sha"
        self.execute("pair-extraordinaire")
        update = next(p for m, path, p in self.primary.calls if m == "PUT" and "/contents/" in path)
        self.assertEqual(update["sha"], "old-content-sha")
        self.assertTrue(update["message"].endswith("\n\nCo-authored-by: Bob <bob@example.com>"))
        self.assertEqual(json.loads(base64.b64decode(update["content"]))["workflow"], "pair-extraordinaire")

    def test_custom_pair_messages_reach_all_api_payloads_and_preserve_credit(self):
        self.runner.config = replace(self.config, pr_title="Save {badge} record",
                                     pr_body="Record details for {repo}\\nFile: {path}",
                                     commit_message="Save co-authored activity\\n\\nUpdate {path}",
                                     merge_title="Include {badge} record",
                                     merge_message="Keep the activity record in {repo}")
        self.execute("pair-extraordinaire")
        operation = self.store.history()[0]["id"]
        expected = render_messages(self.runner.config, "pair-extraordinaire", operation,
                                   coauthor=("Bob", "bob@example.com"))
        update = next(p for m, path, p in self.primary.calls if m == "PUT" and "/contents/" in path)
        pr = next(p for m, path, p in self.primary.calls if m == "POST" and path.endswith("/pulls"))
        merge = next(p for m, path, p in self.primary.calls if path.endswith("/merge"))
        self.assertEqual(pr["title"], expected["pr_title"])
        self.assertEqual(pr["body"], expected["pr_body"])
        self.assertEqual(update["message"], expected["commit_message"])
        self.assertEqual(merge["commit_title"], expected["merge_title"])
        self.assertEqual(merge["commit_message"], expected["merge_message"])
        self.assertTrue(update["message"].endswith("Co-authored-by: Bob <bob@example.com>"))
        self.assertTrue(any("query CommitAuthors" in path for _, path, _ in self.primary.calls))

    def test_invalid_merge_template_fails_before_any_api_calls(self):
        self.runner.config = replace(self.config, merge_message="Invalid {unknown}")
        with self.assertRaisesRegex(ValueError, "MERGE_MESSAGE"):
            self.execute("pull-shark")
        self.assertEqual(self.primary.calls, [])
        self.assertEqual(self.store.history(), [])

    def test_file_selection_continues_across_restarts_and_failed_attempts(self):
        self.execute("pull-shark")
        failed = self.store.start("alice", "alice/lab", "pull-shark")
        self.store.finish(failed, "failed")
        self.store.start("bob", "alice/lab", "pull-shark")
        self.store.start("alice", "alice/other", "pull-shark")
        self.store.start("alice", "alice/lab", "pair-extraordinaire")
        primary = FakeGitHub()
        runner = WorkflowRunner(self.config, primary)
        runner.preflight("pull-shark")
        with StateStore(Path(self.temp.name) / "progress.sqlite3") as reopened:
            runner.run_one("pull-shark", reopened)
            latest = reopened.history(account="alice", repo="alice/lab")[0]
            self.assertEqual(latest["detail"]["message_index"], 3)
            self.assertEqual(reopened.attempt_count("ALICE", "ALICE/LAB", "pull-shark"), 3)
        expected = render_messages(self.config, "pull-shark", latest["id"], message_index=2)
        pr = next(p for method, path, p in primary.calls if method == "POST" and path.endswith("/pulls"))
        self.assertEqual(pr["title"], expected["pr_title"])
        self.assertEqual(pr["body"], expected["pr_body"])

    def test_message_length_with_resolved_coauthor_is_checked_before_writes(self):
        self.runner.preflight("pair-extraordinaire")
        self.runner.coauthor_name = "B" * 65536
        with self.assertRaisesRegex(ValueError, "COMMIT_MESSAGE exceeds"):
            self.runner.run_one("pair-extraordinaire", self.store)
        self.assertFalse(any(method in {"POST", "PUT", "PATCH", "DELETE"}
                             for method, _, _ in self.primary.calls))
        self.assertEqual(self.store.history()[0]["status"], "failed")

    def test_pair_requires_helper_and_rejects_self_pairing_before_writes(self):
        self.runner.config = replace(self.config, helper_token="")
        with self.assertRaisesRegex(ValueError, "HELPER_TOKEN"):
            self.runner.preflight("pair-extraordinaire")
        self.assertEqual(self.primary.calls, [])
        self.runner.config = self.config
        self.helper.user["id"] = self.primary.user["id"]
        with self.assertRaisesRegex(ValueError, "different"):
            self.runner.preflight("pair-extraordinaire")
        self.assertTrue(all(method == "GET" for method, _, _ in self.primary.calls + self.helper.calls))

    def test_pair_resolves_identity_without_helper_repository_access(self):
        self.runner.config = replace(self.config, coauthor_name="", coauthor_email="")
        self.helper.repo["permissions"]["push"] = False
        result = self.execute("pair-extraordinaire")
        self.assertTrue(result["verified"])
        payload = next(p for m, path, p in self.primary.calls if m == "PUT" and "/contents/" in path)
        self.assertIn("Co-authored-by: bob <2+bob@users.noreply.github.com>", payload["message"])
        self.assertEqual(self.helper.calls, [("GET", "/user", None)])

    def test_pair_rejects_email_not_owned_by_helper(self):
        self.runner.config = replace(self.config, coauthor_email="someone-else@example.com")
        with self.assertRaisesRegex(ValueError, "not a verified email"):
            self.runner.preflight("pair-extraordinaire")
        self.assertFalse(any(m != "GET" for m, _, _ in self.primary.calls))

    def test_unrecognized_coauthor_stops_before_opening_pr(self):
        self.primary.author_logins = ["alice"]
        with self.assertRaisesRegex(GitHubError, "not linked both authors"):
            self.execute("pair-extraordinaire")
        self.assertFalse(any(path.endswith("/pulls") for _, path, _ in self.primary.calls))
        self.assertEqual(self.store.count("alice", "alice/lab", "pair-extraordinaire"), 0)
        self.assertEqual(self.store.history()[0]["detail"]["stage"], "verify_coauthors")
        self.assertEqual(self.sleeps, [2, 2, 2])

    def test_mergeability_can_be_eventually_available(self):
        self.primary.mergeability = [None, None, True]
        self.execute("pull-shark")
        self.assertEqual(self.sleeps, [2, 2])

    def test_conflicts_and_unknown_mergeability_never_merge(self):
        for mergeable in (False, None):
            self.primary.calls.clear()
            self.primary.mergeability = [mergeable]
            with self.assertRaises(GitHubError):
                self.execute("pull-shark")
            self.assertFalse(any(path.endswith("/merge") for _, path, _ in self.primary.calls))

    def test_yolo_with_review_does_not_merge(self):
        self.primary.reviews = [{"state": "APPROVED"}]
        with self.assertRaisesRegex(GitHubError, "has a review"):
            self.execute("yolo")
        self.assertFalse(any(path.endswith("/merge") for _, path, _ in self.helper.calls))
        self.assertEqual(self.store.count("alice", "alice/lab", "yolo"), 0)

    def test_readback_rejects_different_answer_author(self):
        self.primary.accepted_author = "someone-else"
        with self.assertRaisesRegex(GitHubError, "could not be verified"):
            self.execute("galaxy-brain")
        self.assertEqual(self.store.count("alice", "alice/lab", "galaxy-brain"), 0)

    def test_failed_merge_keeps_branch_and_does_not_count(self):
        self.primary.merge_error = GitHubError("Branch protected", 405)
        with self.assertRaises(GitHubError):
            self.execute("pull-shark")
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.primary.calls))
        self.assertEqual(self.store.count("alice", "alice/lab", "pull-shark"), 0)
        row = self.store.history()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["detail"]["number"], 7)
        self.assertTrue(row["detail"]["branch"].startswith("achievement/pull-shark/"))

    def test_false_merge_response_is_failure(self):
        self.primary.merge_result = {"merged": False, "message": "Not ready"}
        with self.assertRaisesRegex(GitHubError, "not merged"):
            self.execute("pull-shark")
        self.assertEqual(self.store.history()[0]["status"], "failed")

    def test_cleanup_failure_preserves_success(self):
        self.primary.cleanup_error = GitHubError("Cannot delete", 403)
        result = self.execute("pull-shark")
        self.assertIn("cleanup failed", result["warning"])
        self.assertEqual(self.store.count("alice", "alice/lab", "pull-shark"), 1)

    def test_already_deleted_branch_is_success(self):
        self.primary.cleanup_error = GitHubError("Missing", 404)
        self.assertIsNone(self.execute("pull-shark")["warning"])

    def test_interrupt_is_journaled_without_replay(self):
        self.primary.merge_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.execute("pull-shark")
        self.assertEqual(self.store.history()[0]["status"], "interrupted")

    def test_yolo_uses_helper_only_for_merge(self):
        self.execute("yolo")
        self.assertTrue(any(path.endswith("/merge") for _, path, _ in self.helper.calls))
        self.assertFalse(any(path.endswith("/merge") for _, path, _ in self.primary.calls))

    def test_same_helper_account_rejected_before_writes(self):
        self.helper.user["id"] = 1
        with self.assertRaisesRegex(ValueError, "different"):
            self.runner.preflight("yolo")
        self.assertTrue(all(method == "GET" for method, _, _ in self.primary.calls + self.helper.calls))

    def test_foreign_repository_rejected(self):
        self.primary.repo["owner"]["login"] = "someone-else"
        with self.assertRaisesRegex(ValueError, "owned"):
            self.runner.preflight("pull-shark")

    def test_preflight_rejects_disabled_features(self):
        for feature, workflow in (("has_issues", "quickdraw"), ("has_discussions", "galaxy-brain"), ("allow_merge_commit", "pull-shark")):
            with self.subTest(feature=feature):
                self.primary.repo[feature] = False
                with self.assertRaises(ValueError):
                    self.runner.preflight(workflow)
                self.primary.repo[feature] = True

    def test_quickdraw_validates_github_timestamps(self):
        self.assertEqual(self.execute("quickdraw")["elapsed_seconds"], 8)

    def test_late_issue_closure_not_counted(self):
        self.primary.close_time = "2026-01-01T00:05:01Z"
        with self.assertRaisesRegex(GitHubError, "outside"):
            self.execute("quickdraw")
        self.assertEqual(self.store.count("alice", "alice/lab", "quickdraw"), 0)
        self.assertEqual(self.store.history()[0]["detail"]["number"], 8)

    def test_galaxy_brain_correct_account_roles(self):
        self.execute("galaxy-brain")
        primary_mutations = [q for m, q, _ in self.primary.calls if m == "GRAPHQL" and "mutation" in q]
        helper_mutations = [q for m, q, _ in self.helper.calls if m == "GRAPHQL"]
        self.assertEqual(len(primary_mutations), 1)
        self.assertIn("AddAnswer", primary_mutations[0])
        self.assertIn("CreateQuestion", helper_mutations[0])
        self.assertIn("AcceptAnswer", helper_mutations[1])
        self.assertEqual(self.store.count("alice", "alice/lab", "galaxy-brain"), 1)

    def test_category_selection_paginates(self):
        self.runner.config = replace(self.config, category_id="selected")
        self.primary.category_pages = [
            {"repository": {"id": "repo-id", "discussionCategories": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}},
            {"repository": {"id": "repo-id", "discussionCategories": {"nodes": [{"id": "selected", "name": "Help", "isAnswerable": True}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}},
        ]
        self.runner.preflight("galaxy-brain")
        calls = [p for m, _, p in self.primary.calls if m == "GRAPHQL"]
        self.assertEqual(calls[1]["cursor"], "next")
        self.assertEqual(self.runner.category["id"], "selected")

    def test_history_reset_preserves_tree_and_backup(self):
        self.runner.preflight("reset-history")
        result = self.runner.reset_history("base-sha", self.store)
        writes = [(m, path, p) for m, path, p in self.primary.calls if m != "GET"]
        self.assertTrue(writes[0][2]["ref"].startswith("refs/heads/achievement-backup/"))
        self.assertEqual(writes[0][2]["sha"], "base-sha")
        self.assertEqual(writes[1][2]["tree"], "original-tree")
        self.assertEqual(writes[1][2]["parents"], [])
        self.assertEqual(writes[2][2], {"sha": "new-root", "force": True})
        self.assertEqual(result["new_sha"], "new-root")

    def test_reset_rejects_stale_head_before_mutation(self):
        self.runner.preflight("reset-history")
        with self.assertRaisesRegex(ValueError, "Head changed"):
            self.runner.reset_history("stale", self.store)
        self.assertTrue(all(m == "GET" for m, _, _ in self.primary.calls))

    def test_reset_stops_if_head_changes_while_preparing(self):
        self.runner.preflight("reset-history")
        self.primary.heads = ["base-sha", "new-concurrent-head"]
        with self.assertRaisesRegex(ValueError, "changed during reset"):
            self.runner.reset_history("base-sha", self.store)
        self.assertFalse(any(m == "PATCH" for m, _, _ in self.primary.calls))
        self.assertIn("backup_branch", self.store.history()[0]["detail"])
