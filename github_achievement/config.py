import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .messages import MESSAGE_FILES


def read_env(path: Path) -> dict[str, str]:
    """Read literal KEY=value pairs. Never evaluate shell expressions."""
    if not path.exists():
        return {}
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid environment entry at {path}:{number}.")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unclosed quote at {path}:{number}.")
            value = value[1:-1]
        values[key] = value
    return values


def validate_repo(repo: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Repository must be OWNER/REPO, for example alice/achievement-lab.")
    if repo.split("/")[1] in {".", ".."}:
        raise ValueError("Invalid repository name.")
    return repo


@dataclass(frozen=True)
class Config:
    repo: str = ""
    token: str = field(default="", repr=False)
    helper_token: str = field(default="", repr=False)
    coauthor_name: str = ""
    coauthor_email: str = ""
    category_id: str = ""
    pr_title: str = ""
    pr_body: str = ""
    commit_message: str = ""
    merge_title: str = ""
    merge_message: str = ""
    messages_dir: Path | None = None

    @classmethod
    def load(cls, path: Path, environ: Mapping[str, str] | None = None, repo: str | None = None):
        env = dict(os.environ if environ is None else environ)
        values = read_env(path)
        values.update(env)
        # Shell credentials override file credentials, including the GH_TOKEN alias.
        token = (env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
                 or values.get("GITHUB_TOKEN") or values.get("GH_TOKEN", ""))
        messages_dir = values.get("MESSAGES_DIR", "")
        return cls(repo=repo or values.get("TARGET_REPO", ""), token=token,
                   helper_token=values.get("HELPER_TOKEN", ""),
                   coauthor_name=values.get("COAUTHOR_NAME", ""),
                   coauthor_email=values.get("COAUTHOR_EMAIL", ""),
                   category_id=values.get("DISCUSSION_CATEGORY_ID", ""),
                   messages_dir=(path.parent / messages_dir).resolve() if messages_dir else None,
                   **{key: values.get(key.upper(), "") for key in MESSAGE_FILES})

    def validate(self, workflow: str | None = None, *, credentials: bool = False):
        validate_repo(self.repo)
        if credentials and not self.token:
            raise ValueError("Set GITHUB_TOKEN (or GH_TOKEN) in your environment or .env file.")
        for token in (self.token, self.helper_token):
            if any(c.isspace() for c in token):
                raise ValueError("Tokens must not contain whitespace.")
        if workflow in {"pair-extraordinaire", "yolo", "galaxy-brain"} and credentials and not self.helper_token:
            raise ValueError(f"{workflow} requires HELPER_TOKEN for a different GitHub account.")
        if workflow == "pair-extraordinaire" and credentials:
            if self.coauthor_name and (not self.coauthor_name.strip() or any(c in self.coauthor_name for c in "\r\n<>")):
                raise ValueError("Set COAUTHOR_NAME to your collaborator's commit name.")
            if self.coauthor_email and not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", self.coauthor_email):
                raise ValueError("Set COAUTHOR_EMAIL to your collaborator's GitHub commit email.")

    def redact(self, message: str) -> str:
        for secret in sorted((self.token, self.helper_token), key=len, reverse=True):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message
