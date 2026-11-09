import base64
import json
import time
from datetime import datetime
from urllib.parse import quote, urlencode

from .api import GitHubError
from .cleanup import delete_merged_branch


CATEGORIES_QUERY = """query Categories($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    id discussionCategories(first: 100, after: $cursor) {
      nodes { id name isAnswerable }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""
CREATE_DISCUSSION = """mutation CreateQuestion($input: CreateDiscussionInput!) {
  createDiscussion(input: $input) { discussion { id url } }
}"""
ADD_ANSWER = """mutation AddAnswer($input: AddDiscussionCommentInput!) {
  addDiscussionComment(input: $input) { comment { id url } }
}"""
ACCEPT_ANSWER = """mutation AcceptAnswer($input: MarkDiscussionCommentAsAnswerInput!) {
  markDiscussionCommentAsAnswer(input: $input) {
    discussion { id isAnswered answer { id } }
  }
}"""
COMMIT_AUTHORS = """query CommitAuthors($owner: String!, $name: String!, $sha: GitObjectID!) {
  repository(owner: $owner, name: $name) {
    object(oid: $sha) { ... on Commit { authors(first: 100) { nodes { user { login } } } } }
  }
}"""
VERIFY_ANSWER = """query VerifyAnswer($id: ID!) {
  node(id: $id) { ... on Discussion { isAnswered answer { id author { login } } } }
}"""


class WorkflowRunner:
    def __init__(self, config, primary, helper=None, *, report=None, sleep=time.sleep):
        self.config, self.primary, self.helper = config, primary, helper
        self.report = report or (lambda message: None)
        self.sleep = sleep
        self.prefix = f"/repos/{config.repo}"
        self.user = None
        self.repository = None
        self.category = None
        self.repository_id = None
        self.helper_user = None
        self.coauthor_name = ""
        self.coauthor_email = ""

    def preflight(self, workflow=None):
        self.config.validate(workflow, credentials=True)
        self.report("Checking primary account and repository access")
        self.user = self.primary.request("GET", "/user")
        self.repository = self.primary.request("GET", self.prefix)
        owner = self.repository["owner"]["login"]
        if owner.lower() != self.user["login"].lower():
            raise ValueError("The target must be a personal repository owned by the primary token's account.")
        if self.repository.get("archived") or self.repository.get("disabled"):
            raise ValueError("The target repository is archived or disabled.")
        if not self.repository.get("permissions", {}).get("push"):
            raise ValueError("The primary account needs write access to the repository.")
        if workflow in {"pull-shark", "pair-extraordinaire", "yolo", "reset-history"}:
            if not self.repository.get("default_branch"):
                raise ValueError("Initialize the repository with a commit before running this workflow.")
            self.head()  # An empty repository can still report a default branch name.
        if workflow in {"pull-shark", "pair-extraordinaire", "yolo"}:
            if self.repository.get("allow_merge_commit") is False:
                raise ValueError("Enable merge commits for this repository; this workflow preserves commit authorship.")
        if workflow == "quickdraw" and not self.repository.get("has_issues"):
            raise ValueError("Enable Issues in the target repository's settings.")
        if workflow in {"pair-extraordinaire", "yolo", "galaxy-brain"}:
            if self.helper is None:
                raise ValueError("A helper client is required.")
            self.report("Verifying the helper account")
            helper_user = self.helper_user = self.helper.request("GET", "/user")
            if helper_user["id"] == self.user["id"]:
                raise ValueError("HELPER_TOKEN must belong to a different GitHub account.")
            if workflow in {"yolo", "galaxy-brain"}:
                helper_repo = self.helper.request("GET", self.prefix)
                if not helper_repo.get("permissions", {}).get("push"):
                    raise ValueError("The helper account needs an accepted collaborator invitation and a classic PAT with repo scope.")
            else:
                self.resolve_coauthor()
        if workflow == "galaxy-brain":
            if not self.repository.get("has_discussions"):
                raise ValueError("Enable Discussions and an answerable category (such as Q&A) in repository settings.")
            self.find_category()
        return {"account": self.user["login"], "repo": self.repository["full_name"],
                "default_branch": self.repository.get("default_branch"),
                "issues": self.repository.get("has_issues", False),
                "discussions": self.repository.get("has_discussions", False),
                "private": self.repository.get("private", False),
                "helper": self.helper_user["login"] if self.helper_user else None}

    def resolve_coauthor(self):
        user = self.helper_user
        name = self.config.coauthor_name or user.get("name") or user["login"]
        self.coauthor_name = name if not any(c in name for c in "\r\n<>") else user["login"]
        noreply = f"{user['id']}+{user['login']}@users.noreply.github.com"
        self.coauthor_email = self.config.coauthor_email or noreply
        if self.config.coauthor_email and self.coauthor_email.lower() not in {
            noreply.lower(), f"{user['login']}@users.noreply.github.com".lower()
        }:
            try:
                emails = self.helper.request("GET", "/user/emails")
            except GitHubError as exc:
                raise ValueError("To verify a custom co-author email, give the helper token user:email access, or omit COAUTHOR_EMAIL to use GitHub noreply.") from exc
            if not any(item.get("verified") and item["email"].lower() == self.coauthor_email.lower() for item in emails):
                raise ValueError("COAUTHOR_EMAIL is not a verified email of the helper account.")

    def verify_coauthors(self, sha):
        owner, name = self.config.repo.split("/")
        expected = {self.user["login"].lower(), self.helper_user["login"].lower()}
        for attempt in range(4):
            data = self.primary.graphql(COMMIT_AUTHORS, {"owner": owner, "name": name, "sha": sha})
            commit = (data.get("repository") or {}).get("object") or {}
            authors = (commit.get("authors") or {}).get("nodes", [])
            actual = {(author.get("user") or {}).get("login", "").lower() for author in authors}
            if expected.issubset(actual):
                return
            if attempt < 3:
                self.sleep(2)
        raise GitHubError("GitHub has not linked both authors to the commit. Check the helper's commit email; the branch is preserved and no PR was merged.")

    def wait_for_mergeable(self, number, sha, workflow):
        for attempt in range(5):
            pr = self.primary.request("GET", f"{self.prefix}/pulls/{number}")
            if pr["head"]["sha"] != sha:
                raise GitHubError("The PR head changed; inspect it before merging.")
            if pr.get("draft") or pr.get("state") != "open":
                raise GitHubError("The PR is no longer open and ready for merging.")
            if pr.get("mergeable") is False:
                raise GitHubError("The PR has merge conflicts. Resolve them before continuing.")
            if pr.get("mergeable") is True:
                if workflow == "yolo":
                    self.verify_no_reviews(number)
                return
            if attempt < 4:
                self.sleep(2)
        raise GitHubError("GitHub is still calculating mergeability. The open PR is preserved for inspection.")

    def verify_no_reviews(self, number):
        if self.primary.request("GET", f"{self.prefix}/pulls/{number}/reviews?per_page=1"):
            raise GitHubError("This PR has a review and cannot be counted as a YOLO workflow.")

    def verify_merge(self, number, sha, workflow):
        for attempt in range(4):
            pr = self.primary.request("GET", f"{self.prefix}/pulls/{number}")
            if pr.get("merged") and pr["head"]["sha"] == sha:
                if workflow == "yolo":
                    if (pr.get("merged_by") or {}).get("id") != self.helper_user["id"]:
                        raise GitHubError("The merge was not attributed to the expected helper account.")
                    self.verify_no_reviews(number)
                return
            if attempt < 3:
                self.sleep(2)
        raise GitHubError("Merge response received, but read-back verification is pending. Inspect the PR before starting another operation.")

    def head(self):
        branch = quote(self.repository["default_branch"], safe="")
        return self.primary.request("GET", f"{self.prefix}/git/ref/heads/{branch}")["object"]["sha"]

    def find_category(self):
        owner, name = self.config.repo.split("/")
        cursor = None
        while True:
            data = self.primary.graphql(CATEGORIES_QUERY, {"owner": owner, "name": name, "cursor": cursor})
            repository = data.get("repository")
            if not repository:
                raise ValueError("The target repository is not accessible through GraphQL.")
            self.repository_id = repository["id"]
            categories = repository["discussionCategories"]
            for category in categories["nodes"]:
                if category["isAnswerable"] and (not self.config.category_id or category["id"] == self.config.category_id):
                    self.category = category
                    return
            page = categories["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]
        raise ValueError("No matching answerable discussion category. Enable Q&A or check DISCUSSION_CATEGORY_ID.")

    def run_one(self, workflow, store):
        if self.user is None:
            raise ValueError("Run preflight before executing a workflow.")
        operation_id = store.start(self.user["login"], self.config.repo, workflow)

        def checkpoint(**detail):
            store.checkpoint(operation_id, **detail)
            if "stage" in detail:
                self.report(detail["stage"].replace("_", " ").capitalize())

        try:
            if workflow == "quickdraw":
                result = self.quickdraw(operation_id, checkpoint)
            elif workflow == "galaxy-brain":
                result = self.galaxy_brain(operation_id, checkpoint)
            else:
                result = self.pull_request(workflow, operation_id, checkpoint)
            store.finish(operation_id, **result)
            return result
        except KeyboardInterrupt:
            store.finish(operation_id, "interrupted", error="Interrupted; inspect remote resources before starting another operation.")
            raise
        except Exception as exc:
            store.finish(operation_id, "failed", error=self.config.redact(str(exc)))
            raise

    def pull_request(self, workflow, operation_id, checkpoint):
        branch = f"achievement/{workflow}/{operation_id}"
        path = f".github-achievements/{workflow}.json"
        base_sha = self.head()
        checkpoint(stage="create_branch", branch=branch, base_sha=base_sha)
        self.primary.request("POST", f"{self.prefix}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha})
        checkpoint(stage="create_commit")
        file_url = f"{self.prefix}/contents/{path}"
        existing_sha = None
        try:
            existing_sha = self.primary.request("GET", file_url + "?" + urlencode({"ref": base_sha}))["sha"]
        except GitHubError as exc:
            if exc.status != 404:
                raise
        message = f"Record {workflow} workflow {operation_id[:8]}"
        if workflow == "pair-extraordinaire":
            message += f"\n\nCo-authored-by: {self.coauthor_name} <{self.coauthor_email}>"
        content = json.dumps({"workflow": workflow, "operation": operation_id}, indent=2) + "\n"
        payload = {"message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch}
        if existing_sha:
            payload["sha"] = existing_sha
        commit = self.primary.request("PUT", file_url, payload)
        commit_sha = commit["commit"]["sha"]
        if workflow == "pair-extraordinaire":
            checkpoint(stage="verify_coauthors", commit_sha=commit_sha)
            self.verify_coauthors(commit_sha)
        checkpoint(stage="open_pull_request", commit_sha=commit_sha)
        pr = self.primary.request("POST", f"{self.prefix}/pulls", {
            "title": f"Achievement workflow: {workflow} ({operation_id[:8]})",
            "head": branch, "base": self.repository["default_branch"],
            "body": f"Created by github-achievement-python.\n\nWorkflow: {workflow}\nOperation: {operation_id}",
        })
        checkpoint(stage="check_mergeability", number=pr["number"], url=pr["html_url"])
        self.wait_for_mergeable(pr["number"], commit_sha, workflow)
        checkpoint(stage="merge_pull_request")
        merger = self.helper if workflow == "yolo" else self.primary
        merged = merger.request("PUT", f"{self.prefix}/pulls/{pr['number']}/merge", {
            "merge_method": "merge", "sha": commit_sha,
        })
        if not merged.get("merged"):
            raise GitHubError(f"PR #{pr['number']} was not merged: {merged.get('message', 'unknown reason')}")
        checkpoint(stage="verify_merge", merged=True, merge_sha=merged.get("sha"))
        self.verify_merge(pr["number"], commit_sha, workflow)
        checkpoint(stage="delete_branch", verified=True)
        warning = None
        try:
            cleanup = delete_merged_branch(self.primary, self.config.repo, branch, commit_sha)
            if cleanup["status"] == "kept":
                warning = f"PR merged; branch kept: {cleanup['reason']}"
        except GitHubError as exc:
            warning = self.config.redact(f"PR merged; branch cleanup failed for {branch}: {exc}")
            cleanup = {"status": "error", "reason": warning, "rate_limited": exc.retry_after is not None}
        return {"stage": "complete", "url": pr["html_url"], "warning": warning, "verified": True, "cleanup": cleanup}

    def quickdraw(self, operation_id, checkpoint):
        checkpoint(stage="open_issue")
        issue = self.primary.request("POST", f"{self.prefix}/issues", {
            "title": f"Quickdraw workflow ({operation_id[:8]})",
            "body": f"Issue lifecycle exercise created by github-achievement-python.\nOperation: {operation_id}",
        })
        checkpoint(stage="close_issue", number=issue["number"], url=issue["html_url"])
        self.primary.request("PATCH", f"{self.prefix}/issues/{issue['number']}", {"state": "closed"})
        checkpoint(stage="verify_issue_closure")
        closed = self.primary.request("GET", f"{self.prefix}/issues/{issue['number']}")
        if closed.get("state") != "closed" or not closed.get("closed_at"):
            raise GitHubError("GitHub did not confirm issue closure.")
        elapsed = (datetime.fromisoformat(closed["closed_at"].replace("Z", "+00:00"))
                   - datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))).total_seconds()
        if not 0 <= elapsed < 300:
            raise GitHubError(f"Issue closed, but outside the Quickdraw window ({elapsed:.0f} seconds).")
        return {"stage": "complete", "url": issue["html_url"], "elapsed_seconds": elapsed, "verified": True}

    def galaxy_brain(self, operation_id, checkpoint):
        checkpoint(stage="create_discussion")
        result = self.helper.graphql(CREATE_DISCUSSION, {"input": {
            "repositoryId": self.repository_id, "categoryId": self.category["id"],
            "title": f"How does this discussion workflow work? ({operation_id[:8]})",
            "body": f"Testing the question and accepted-answer workflow in this repository.\nOperation: {operation_id}",
        }}, mutation=True)
        discussion = result["createDiscussion"]["discussion"]
        checkpoint(stage="answer_discussion", discussion_id=discussion["id"], url=discussion["url"])
        result = self.primary.graphql(ADD_ANSWER, {"input": {
            "discussionId": discussion["id"],
            "body": "An answerable discussion category lets the question author mark a reply as the accepted answer.",
        }}, mutation=True)
        comment = result["addDiscussionComment"]["comment"]
        checkpoint(stage="accept_answer", comment_id=comment["id"])
        result = self.helper.graphql(ACCEPT_ANSWER, {"input": {"id": comment["id"]}}, mutation=True)
        accepted = result["markDiscussionCommentAsAnswer"]["discussion"]
        if not accepted.get("isAnswered") or (accepted.get("answer") or {}).get("id") != comment["id"]:
            raise GitHubError("GitHub did not confirm the expected accepted answer.")
        checkpoint(stage="verify_accepted_answer")
        verified = self.primary.graphql(VERIFY_ANSWER, {"id": discussion["id"]}).get("node") or {}
        answer = verified.get("answer") or {}
        if (not verified.get("isAnswered") or answer.get("id") != comment["id"]
                or (answer.get("author") or {}).get("login", "").lower() != self.user["login"].lower()):
            raise GitHubError("The accepted answer could not be verified for the primary account.")
        return {"stage": "complete", "url": discussion["url"], "verified": True}

    def reset_history(self, expected_head, store):
        """Keep the file tree, preserve an old-head backup ref, and create a root commit."""
        current = self.head()
        if current != expected_head:
            raise ValueError(f"Head changed. Expected {expected_head}, found {current}; preview again.")
        operation_id = store.start(self.user["login"], self.config.repo, "reset-history")
        backup = f"achievement-backup/{operation_id}"
        try:
            store.checkpoint(operation_id, stage="create_backup", backup_branch=backup, original_sha=current)
            self.primary.request("POST", f"{self.prefix}/git/refs", {"ref": f"refs/heads/{backup}", "sha": current})
            commit = self.primary.request("GET", f"{self.prefix}/git/commits/{current}")
            store.checkpoint(operation_id, stage="create_root_commit")
            root = self.primary.request("POST", f"{self.prefix}/git/commits", {
                "message": "Reset repository history (previous history preserved on backup branch)",
                "tree": commit["tree"]["sha"], "parents": [],
            })
            if self.head() != current:
                raise ValueError("The default branch changed during reset; no force update was sent.")
            store.checkpoint(operation_id, stage="update_default_branch", new_sha=root["sha"])
            branch = quote(self.repository["default_branch"], safe="")
            self.primary.request("PATCH", f"{self.prefix}/git/refs/heads/{branch}", {"sha": root["sha"], "force": True})
            result = {"stage": "complete", "backup_branch": backup, "new_sha": root["sha"]}
            store.finish(operation_id, **result)
            return result
        except KeyboardInterrupt:
            store.finish(operation_id, "interrupted", error="Interrupted; inspect default and backup branches.")
            raise
        except Exception as exc:
            store.finish(operation_id, "failed", error=self.config.redact(str(exc)))
            raise
