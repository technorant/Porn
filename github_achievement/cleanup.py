"""Remove recorded, merged workflow branches without touching other repository data."""
import re
from urllib.parse import quote

from .api import GitHubError


def delete_merged_branch(client, repo, branch, expected_sha, *, execute=True):
    prefix = f"/repos/{repo}/git"
    escaped = quote(branch, safe="")
    lookup = f"{prefix}/ref/heads/{escaped}"
    try:
        actual = client.request("GET", lookup)["object"]["sha"]
    except GitHubError as exc:
        if exc.status == 404:
            return {"status": "already_clean", "reason": "Branch is already gone."}
        raise
    if actual != expected_sha:
        return {"status": "kept", "reason": "Branch changed after the recorded commit; inspect it manually."}
    if not execute:
        return {"status": "ready", "reason": "Merged branch can be removed."}
    try:
        client.request("DELETE", f"{prefix}/refs/heads/{escaped}")
    except GitHubError as exc:
        if exc.status in {404, 422}:
            # GitHub's automatic branch deletion can race this request.
            try:
                client.request("GET", lookup)
            except GitHubError as lookup_error:
                if lookup_error.status == 404:
                    return {"status": "already_clean", "reason": "GitHub already removed the branch."}
                raise
        raise
    return {"status": "deleted", "reason": "Removed the merged workflow branch."}


def cleanup_record(runner, record, *, execute=False):
    detail = record["detail"]
    branch, sha, number = detail.get("branch"), detail.get("commit_sha"), detail.get("number")
    workflow = record["workflow"]
    expected_branch = f"achievement/{workflow}/{record['id']}"
    if (workflow not in {"pull-shark", "pair-extraordinaire", "yolo"}
            or not re.fullmatch(r"[a-f0-9]{32}", record["id"]) or branch != expected_branch
            or branch == runner.repository["default_branch"]):
        return {"status": "kept", "reason": "Not a recognized temporary workflow branch."}
    if not isinstance(number, int) or isinstance(number, bool) or number < 1 or not sha:
        return {"status": "kept", "reason": "No recorded PR and commit to verify; inspect this unfinished operation."}
    pr = runner.primary.request("GET", f"{runner.prefix}/pulls/{number}")
    head = pr.get("head") or {}
    if not pr.get("merged"):
        return {"status": "kept", "reason": f"PR #{number} is not merged."}
    if ((head.get("repo") or {}).get("full_name", "").lower() != runner.config.repo.lower()
            or head.get("ref") != branch or head.get("sha") != sha
            or (pr.get("user") or {}).get("login", "").lower() != runner.user["login"].lower()):
        return {"status": "kept", "reason": "The PR does not match the recorded branch, author and commit."}
    return delete_merged_branch(runner.primary, runner.config.repo, branch, sha, execute=execute)


def cleanup_tracked(runner, store, *, execute=False):
    results = []
    records = store.history(account=runner.user["login"], repo=runner.config.repo, limit=-1)
    for record in records:
        branch = record["detail"].get("branch")
        if not branch:
            continue
        runner.report(f"Checking cleanup: {branch}")
        try:
            result = cleanup_record(runner, record, execute=execute)
        except GitHubError as exc:
            result = {"status": "error", "reason": runner.config.redact(str(exc))}
            results.append({"branch": branch, **result})
            if execute:
                store.checkpoint(record["id"], cleanup=result)
            # In particular, don't keep making requests after a rate-limit error.
            break
        if execute:
            details = {"cleanup": result}
            if result["status"] in {"deleted", "already_clean"}:
                details["warning"] = None
            store.checkpoint(record["id"], **details)
        results.append({"branch": branch, **result})
    return results
