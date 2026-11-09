"""Literal templates for the actual activity-record changes made by PR workflows."""

import re
from string import Formatter

from .catalog import ACHIEVEMENTS


PR_WORKFLOWS = {"pull-shark", "pair-extraordinaire", "yolo"}
MESSAGE_DEFAULTS = {
    "pr_title": "Record {badge} activity",
    "pr_body": "Update `{path}` with the next {badge} operation record in `{repo}`.",
    "commit_message": "Update {workflow} activity record",
    "merge_title": "Merge {badge} activity record",
    "merge_message": "Include the recorded {workflow} operation in {repo}.",
}
MESSAGE_LABELS = {
    "pr_title": "PR title",
    "pr_body": "PR description",
    "commit_message": "Commit message",
    "merge_title": "Merge commit title",
    "merge_message": "Merge commit description",
}
PREVIEW_OPERATION = "0123456789abcdef0123456789abcdef"
TITLE_FIELDS = {"pr_title", "merge_title"}


def _expand(template, values, field):
    # Decode only the documented newline escape, never arbitrary Python or shell code.
    template = template.replace("\\n", "\n").replace("\r\n", "\n")
    formatter = Formatter()
    try:
        for _, name, spec, conversion in formatter.parse(template):
            if name is not None and (name not in values or spec or conversion):
                raise ValueError
        result = template.format_map(values).strip()
    except (ValueError, KeyError):
        raise ValueError(
            f"{field.upper()}: use only {{badge}}, {{workflow}}, {{repo}}, or {{path}}; "
            "write {{ and }} for literal braces."
        ) from None
    if not result:
        raise ValueError(f"{field.upper()} must contain text, or be empty to use the default.")
    if any(ord(c) < 32 and c not in "\n\t" or 127 <= ord(c) <= 159 for c in result):
        raise ValueError(f"{field.upper()} contains an unsupported control character.")
    if field in TITLE_FIELDS and len(result.splitlines()) != 1:
        raise ValueError(f"{field.upper()} must be a single line.")
    if field in {"commit_message", "merge_title", "merge_message"} and re.search(
        r"^\s*Co-authored-by\s*:", result, re.IGNORECASE | re.MULTILINE
    ):
        raise ValueError("Co-authored-by trailers are added automatically for the verified Pair helper.")
    return result


def render_messages(config, workflow, operation_id, *, coauthor=None):
    """Render all fields before any write; suffixes make each operation traceable."""
    if workflow not in PR_WORKFLOWS:
        raise ValueError("Custom PR messages apply to Pull Shark, Pair Extraordinaire, and YOLO.")
    values = {"badge": ACHIEVEMENTS[workflow].name, "workflow": workflow,
              "repo": config.repo, "path": f".github-achievements/{workflow}.json"}
    messages = {}
    for field, default in MESSAGE_DEFAULTS.items():
        text = _expand(getattr(config, field) or default, values, field)
        if field in TITLE_FIELDS:
            text += f" [{operation_id}]"
        else:
            if field in {"pr_body", "merge_message"}:
                text += "\n\nAutomated workflow run by github-achievement-python."
            text += f"\n\nOperation: {operation_id}"
        if field == "commit_message" and workflow == "pair-extraordinaire" and coauthor:
            name, email = coauthor
            text += f"\n\nCo-authored-by: {name} <{email}>"
        # Conservative UTF-8 byte limits, including generated metadata/trailers.
        limit = 256 if field in TITLE_FIELDS else 65536
        if len(text.encode("utf-8")) > limit:
            raise ValueError(f"{field.upper()} exceeds {limit} UTF-8 bytes including automatic metadata; shorten it.")
        messages[field] = text
    return messages
