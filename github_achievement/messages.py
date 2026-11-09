"""Literal templates for the actual activity-record changes made by PR workflows."""

import re
from pathlib import Path
from string import Formatter

from .catalog import ACHIEVEMENTS


PR_WORKFLOWS = {"pull-shark", "pair-extraordinaire", "yolo"}
MESSAGE_FILES = {
    "pr_title": "prtitle.txt",
    "pr_body": "prdescription.txt",
    "commit_message": "messages.txt",
    "merge_title": "mergetitle.txt",
    "merge_message": "mergedescription.txt",
}
DEFAULT_MESSAGE_DIR = Path(__file__).resolve().parent / "message_files"
MESSAGE_LABELS = {
    "pr_title": "PR title",
    "pr_body": "PR description",
    "commit_message": "Commit message",
    "merge_title": "Merge commit title",
    "merge_message": "Merge commit description",
}
PREVIEW_OPERATION = "0123456789abcdef0123456789abcdef"
TITLE_FIELDS = {"pr_title", "merge_title"}


def message_directory(config):
    return config.messages_dir if config.messages_dir is not None else DEFAULT_MESSAGE_DIR


def load_message_templates(config):
    """Read one template per nonblank, noncomment line; keep a snapshot for the run."""
    templates = {}
    for field, filename in MESSAGE_FILES.items():
        override = getattr(config, field)
        if override:
            templates[field] = (override,)
            continue
        path = message_directory(config) / filename
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeError:
            raise ValueError(f"Message file {path} must be saved as UTF-8.") from None
        except OSError as exc:
            raise ValueError(f"Cannot read message file {path}: {exc.strerror or 'file unavailable'}.") from None
        entries = tuple(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))
        if not entries:
            raise ValueError(f"Message file {path} needs at least one message line.")
        templates[field] = entries
    return templates


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
        raise ValueError(f"{field.upper()} must contain text, or be empty to use its message file.")
    if any(ord(c) < 32 and c not in "\n\t" or 127 <= ord(c) <= 159 for c in result):
        raise ValueError(f"{field.upper()} contains an unsupported control character.")
    if field in TITLE_FIELDS and len(result.splitlines()) != 1:
        raise ValueError(f"{field.upper()} must be a single line.")
    if field in {"commit_message", "merge_title", "merge_message"} and re.search(
        r"^\s*Co-authored-by\s*:", result, re.IGNORECASE | re.MULTILINE
    ):
        raise ValueError("Co-authored-by trailers are added automatically for the verified Pair helper.")
    return result


def _render_field(config, workflow, operation_id, field, template, coauthor):
    values = {"badge": ACHIEVEMENTS[workflow].name, "workflow": workflow,
              "repo": config.repo, "path": f".github-achievements/{workflow}.json"}
    text = _expand(template, values, field)
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
    return text


def validate_message_templates(config, workflow, *, templates=None, coauthor=None):
    """Check every candidate so a bad later entry cannot fail halfway through a batch."""
    if workflow not in PR_WORKFLOWS:
        raise ValueError("Custom PR messages apply to Pull Shark, Pair Extraordinaire, and YOLO.")
    templates = load_message_templates(config) if templates is None else templates
    for field, entries in templates.items():
        for index, template in enumerate(entries, 1):
            try:
                _render_field(config, workflow, PREVIEW_OPERATION, field, template, coauthor)
            except ValueError as exc:
                source = field.upper() if getattr(config, field) else str(message_directory(config) / MESSAGE_FILES[field])
                raise ValueError(f"{source}, entry {index}: {exc}") from None
    return templates


def render_messages(config, workflow, operation_id, *, coauthor=None, message_index=0, templates=None):
    """Select the next entry in each file; suffixes keep cycled messages traceable."""
    if message_index < 0:
        raise ValueError("Message index must not be negative.")
    if templates is None:
        templates = validate_message_templates(config, workflow, coauthor=coauthor)
    return {field: _render_field(config, workflow, operation_id, field,
                                 entries[message_index % len(entries)], coauthor)
            for field, entries in templates.items()}
