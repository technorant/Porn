import getpass
import os
import sys
import tempfile
from dataclasses import replace

from .api import GitHubClient
from .catalog import ACHIEVEMENTS
from .config import Config, read_env, validate_repo
from .ui import Choice, Console


def save_config(config, path):
    config.validate()
    values = read_env(path)
    values.update({"TARGET_REPO": config.repo, "GITHUB_TOKEN": config.token, "HELPER_TOKEN": config.helper_token,
                   "COAUTHOR_NAME": config.coauthor_name, "COAUTHOR_EMAIL": config.coauthor_email,
                   "DISCUSSION_CATEGORY_ID": config.category_id})
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Configuration values must be single-line strings.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".achievement-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Local credentials. Do not commit. Shell variables take precedence.\n")
            for key, value in values.items():
                # Single quotes are literal in this dotenv reader; choose a matching wrapper.
                if value.startswith(('"', "'")) or value != value.strip():
                    if "'" not in value:
                        value = "'" + value + "'"
                    elif '"' not in value:
                        value = '"' + value + '"'
                    else:
                        raise ValueError(f"Unsupported quoting in configuration field {key}.")
                handle.write(f"{key}={value}\n")
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def secret(label, existing=""):
    suffix = " [Enter keeps configured token]" if existing else ""
    while True:
        value = getpass.getpass(f"  {label}{suffix}: ").strip() or existing
        if value and not any(c.isspace() for c in value):
            return value
        print("  Enter a token without whitespace; input stays hidden.")


def helper_credentials(config, workflow, console, *, edit=False):
    if workflow and ACHIEVEMENTS[workflow].helper and (edit or not config.helper_token):
        if workflow == "pair-extraordinaire":
            console.panel("PAIR EXTRAORDINAIRE / connect your co-author", [
                "Use a token from a different GitHub account.",
                "We read its identity and use its GitHub noreply email for co-authorship.",
                "This helper only needs authenticated profile access; it does not merge or write to your repo.",
            ], "gold")
        else:
            console.panel("HELPER ACCOUNT", [
                "Use a classic PAT with repo scope from a different account.",
                "The helper must already have accepted a collaborator invitation.",
            ], "gold")
        config = replace(config, helper_token=secret("Helper token (hidden)", config.helper_token))
    return config


def create_repository(token, console):
    client = GitHubClient(token)
    with console.activity("Checking your GitHub account"):
        user = client.request("GET", "/user")
    login = user["login"]
    console.say(f"Connected as {login}", "green")
    name = console.ask("New repository name", "achievement-lab", required=True,
                       validator=lambda value: validate_repo(f"{login}/{value}"))
    visibility = console.choose("Repository visibility", [
        Choice("public", "Public", "Activity is visible on GitHub"),
        Choice("private", "Private", "Profile visibility depends on your GitHub settings"),
    ])
    if visibility == "back":
        raise ValueError("Repository creation cancelled.")
    console.panel(f"CREATE / {login}/{name}", [f"Visibility: {visibility}", "Initialize with a README and enable Issues."])
    action = console.choose("Create this repository?", [Choice("create", "Create repository"), Choice("back", "Back")])
    if action != "create":
        raise ValueError("Repository creation cancelled.")
    with console.activity("Creating your repository"):
        repository = client.request("POST", "/user/repos", {
            "name": name, "private": visibility == "private", "auto_init": True, "has_issues": True,
            "description": "GitHub achievement workflow lab",
        })
    console.say(f"Created {repository['html_url']}", "green")
    return repository["full_name"]


def setup(config, path, workflow=None):
    if not sys.stdin.isatty():
        raise ValueError("Setup needs an interactive terminal. Copy .env.example to .env or use environment variables.")
    console = Console()
    console.panel("CONNECT / GitHub", ["Tokens are hidden while you type and saved in your local .env.",
                                        "Setup asks for a helper only when your selected workflow needs one."])
    token = secret("Primary GitHub token", config.token)
    choices = [Choice("existing", "Use an existing repository", config.repo or "OWNER/REPO"),
               Choice("create", "Create a repository", "An initialized repository on your account")]
    source = console.choose("Your repository", choices, default=0 if config.repo else 1)
    if source == "back":
        raise ValueError("Setup cancelled.")
    repo = (create_repository(token, console) if source == "create"
            else console.ask("Repository", config.repo, required=True, validator=validate_repo))
    updated = helper_credentials(replace(config, repo=repo, token=token), workflow, console, edit=True)
    updated.validate(workflow, credentials=True)
    save_config(updated, path)
    console.say(f"Saved {path}. Shell values take precedence over this file.", "green")
    return updated


def ensure_credentials(config, path, workflow=None, *, allow_create=True):
    if not sys.stdin.isatty():
        config.validate(workflow, credentials=True)
        return config
    if not config.repo or not config.token:
        if allow_create:
            return setup(config, path, workflow)
        console = Console()
        console.say("Connection checks use an existing repository. Use setup to create one.", "muted")
        config = replace(config, token=config.token or secret("Primary GitHub token"),
                         repo=config.repo or console.ask("Existing repository", required=True, validator=validate_repo))
        config = helper_credentials(config, workflow, console)
        config.validate(workflow, credentials=True)
        save_config(config, path)
        return config
    updated = helper_credentials(config, workflow, Console())
    updated.validate(workflow, credentials=True)
    if updated != config:
        save_config(updated, path)
    return updated
