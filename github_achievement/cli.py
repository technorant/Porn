import argparse
import json
import math
import sqlite3
import sys
import time
from dataclasses import replace
from pathlib import Path

from . import __version__
from .api import GitHubClient, GitHubError, WriteLimiter
from .catalog import ACHIEVEMENTS, TIERS, target_for
from .config import Config
from .state import RunLock, StateStore
from .workflows import WorkflowRunner
from .badges import check_badges
from .onboarding import ensure_credentials, setup
from .ui import Choice, Console


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be at least 1.")
    return number


def interval_value(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Must be a finite, non-negative number.")
    return number


def common_arguments(parser):
    parser.add_argument("--env-file", type=Path, default=argparse.SUPPRESS, help="Configuration file (default: .env)")
    parser.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS, help="Local journal directory (default: .achievement-state)")
    parser.add_argument("--repo", default=argparse.SUPPRESS, help="Target personal repository: OWNER/REPO")


def badge_wait(value):
    number = int(value)
    if not 0 <= number <= 600:
        raise argparse.ArgumentTypeError("Choose between 0 and 600 seconds.")
    return number


def build_parser():
    parser = argparse.ArgumentParser(prog="github-achievement", description="GitHub achievement workflows in Python. Run without a command for the menu.")
    parser.add_argument("--version", action="version", version=__version__)
    common_arguments(parser)
    subs = parser.add_subparsers(dest="command")
    definitions = (
        ("list", "List achievements and community-reported tier thresholds"),
        ("setup", "Configure tokens and repository interactively"),
        ("doctor", "Check authentication and repository access without changing GitHub"),
        ("status", "Show the local operation journal; no network access"),
        ("verify", "Check which badges are visible on your public GitHub profile"),
        ("run", "Preview or execute an achievement workflow"),
        ("reset-history", "Preview or reset the default branch with a backup branch"),
    )
    commands = {}
    for name, help_text in definitions:
        sub = subs.add_parser(name, help=help_text)
        common_arguments(sub)
        commands[name] = sub
    commands["list"].add_argument("--json", action="store_true")
    commands["setup"].add_argument("--workflow", choices=ACHIEVEMENTS, help="Also configure the selected workflow's helper account")
    commands["doctor"].add_argument("--workflow", choices=ACHIEVEMENTS)
    commands["doctor"].add_argument("--json", action="store_true")
    commands["status"].add_argument("--account", help="Filter by authenticated account login")
    commands["status"].add_argument("--history", action="store_true", help="Include recent operations and resource URLs")
    commands["status"].add_argument("--limit", type=positive_int, default=25)
    commands["status"].add_argument("--json", action="store_true")
    commands["verify"].add_argument("--account", help="GitHub username; defaults to target repository owner")
    commands["verify"].add_argument("--achievement", choices=ACHIEVEMENTS)
    commands["verify"].add_argument("--wait", type=badge_wait, default=0, help="Poll public profile for up to this many seconds (max 600)")
    commands["verify"].add_argument("--json", action="store_true")
    run = commands["run"]
    run.add_argument("achievement", choices=ACHIEVEMENTS, nargs="?", help="Omit to choose interactively")
    amount = run.add_mutually_exclusive_group()
    amount.add_argument("--count", type=positive_int, help="Number of new operations (default: 1)")
    amount.add_argument("--tier", choices=TIERS, help="Reach this threshold using locally recorded successes")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Perform the displayed GitHub writes")
    mode.add_argument("--dry-run", action="store_true", help="Preview without credentials or network (the default)")
    run.add_argument("--interval", type=interval_value, default=10.0, help="Seconds between operations; API writes are also paced (default: 10)")
    run.add_argument("--coauthor-name")
    run.add_argument("--coauthor-email")
    run.add_argument("--category-id")
    run.add_argument("--wait-for-badge", type=badge_wait, default=0, help="After successful operations, poll for public badge visibility (max 600 seconds)")
    run.add_argument("--skip-badge-check", action="store_true", help="Only verify API operations; skip the public profile check")
    reset = commands["reset-history"]
    reset.add_argument("--execute", action="store_true")
    reset.add_argument("--expected-head", help="Full SHA from a fresh reset-history preview")
    return parser


def table(headers, rows):
    console = Console()
    rows = [[str(value) for value in row] for row in rows]
    widths = [max([len(header), *(len(row[i]) for row in rows)]) for i, header in enumerate(headers)]
    console.say("  ".join(header.ljust(width) for header, width in zip(headers, widths)), "cyan")
    console.say("  ".join("-" * width for width in widths), "muted")
    for row in rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))


def list_achievements(as_json=False):
    data = [{"id": a.slug, "name": a.name, "thresholds": a.thresholds,
             "description": a.description, "helper_required": a.helper} for a in ACHIEVEMENTS.values()]
    if as_json:
        print(json.dumps(data, indent=2))
        return
    Console().panel("THE ACHIEVEMENT COLLECTION", ["Pick a badge and a target tier from the interactive menu."])
    table(["Achievement", "Base / Bronze / Silver / Gold", "Requires"], [
        [a.slug, " / ".join(map(str, a.thresholds)),
         "Helper account" if a.helper else "Primary account"]
        for a in ACHIEVEMENTS.values()
    ])
    print("\nThresholds are community-reported. GitHub decides when and whether to award badges.")


def make_runner(config):
    limiter = WriteLimiter()
    primary = GitHubClient(config.token, limiter=limiter)
    helper = GitHubClient(config.helper_token, limiter=limiter) if config.helper_token else None
    return WorkflowRunner(config, primary, helper)


def show_status(args, config, state_dir):
    path = state_dir / "progress.sqlite3"
    if not path.exists():
        data = {"summary": [], "history": []}
    else:
        with StateStore(path) as store:
            data = {"summary": store.summary(account=args.account, repo=config.repo),
                    "history": store.history(account=args.account, repo=config.repo, limit=args.limit) if args.history else []}
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print("Local workflow records (these are not verified GitHub badge counts).")
    if not data["summary"]:
        print("No recorded operations.")
        return
    table(["Account", "Repository", "Workflow", "Status", "Count"], [list(row.values()) for row in data["summary"]])
    for row in data["history"]:
        print(f"\n{row['id']}  {row['workflow']}  {row['status']}  {row['started_at']}")
        print(json.dumps(row["detail"], indent=2))


def show_plan(args, config):
    console = Console()
    achievement = ACHIEVEMENTS[args.achievement]
    config.validate()
    if args.tier:
        target = target_for(args.achievement, args.tier)
        amount = f"up to {target} total locally recorded successes ({args.tier}); account checked at execution"
    else:
        amount = f"{args.count or 1} new operation(s)"
    console.panel(f"{achievement.name.upper()} / {config.repo}", [f"Plan: {amount}"])
    for number, step in enumerate(achievement.steps, 1):
        console.say(f"  {number:02}. {step}")
    if achievement.helper:
        console.say("Requires a token from a different helper account.", "gold")
    if args.achievement == "pair-extraordinaire":
        console.say("Co-author identity is resolved from the helper; GitHub must recognize both commit authors.", "muted")


def display_badges(result):
    console = Console()
    console.panel("GITHUB / badge visibility", [result["account"], result["profile_url"]], "gold")
    labels = {"visible": ("VISIBLE ON GITHUB", "green"), "not_visible": ("NOT VISIBLE YET", "gold"), "unknown": ("UNKNOWN", "muted")}
    for slug, status in result["badges"].items():
        label, color = labels[status]
        console.say(f"  {ACHIEVEMENTS[slug].name:<22} {label}", color)
    console.say(result["note"], "muted")


def verify_badges(args, config):
    account = args.account or (config.repo.split("/")[0] if config.repo else "")
    if not account:
        raise ValueError("Use --account YOUR_USERNAME or configure a target repository.")
    selected = [args.achievement] if args.achievement else None
    if args.json:
        result = check_badges(account, selected, wait=args.wait)
        print(json.dumps(result, indent=2))
    else:
        with Console().activity("Checking public GitHub badges") as activity:
            result = check_badges(account, selected, wait=args.wait, report=activity.update)
        display_badges(result)
    return 0 if all(status == "visible" for status in result["badges"].values()) else 3


def execute_run(args, config, state_dir):
    console = Console()
    show_plan(args, config)
    if not args.execute:
        print("\nPreview only. Add --execute to perform these operations on GitHub.")
        return
    config.validate(args.achievement, credentials=True)
    runner = make_runner(config)
    with console.activity("Checking workflow prerequisites") as activity:
        runner.report = activity.update
        info = runner.preflight(args.achievement)
    with RunLock(state_dir), StateStore(state_dir / "progress.sqlite3") as store:
        completed = store.count(info["account"], config.repo, args.achievement)
        count = max(0, target_for(args.achievement, args.tier) - completed) if args.tier else (args.count or 1)
        print(f"\nAuthenticated as {info['account']}. {completed} recorded successes; {count} operation(s) to run.")
        if info.get("helper"):
            console.say(f"Helper verified: {info['helper']}", "green")
        console.progress(0, count)
        for index in range(count):
            if index:
                with console.activity(f"Next operation in {args.interval:g} seconds"):
                    time.sleep(args.interval)
            with console.activity(f"Operation {index + 1} of {count}") as activity:
                runner.report = activity.update
                result = runner.run_one(args.achievement, store)
            console.say(f"  VERIFIED  {result['url']}", "green")
            console.progress(index + 1, count)
            if result.get("warning"):
                print(result["warning"], file=sys.stderr)
        console.say("Workflow results verified and saved.", "green")
    if not args.skip_badge_check:
        with console.activity("Checking whether GitHub displays the badge") as activity:
            result = check_badges(info["account"], [args.achievement], wait=args.wait_for_badge, report=activity.update)
        display_badges(result)
    else:
        console.say("Public badge check skipped. Run verify when you want to check your profile.", "muted")


def reset_history(args, config, state_dir):
    config.validate(credentials=True)
    runner = make_runner(config)
    info = runner.preflight("reset-history")
    head = runner.head()
    print(f"Repository: {config.repo}\nDefault branch: {info['default_branch']}\nCurrent head: {head}")
    print("This creates a backup branch, then replaces default-branch history with one commit keeping the same files.")
    print("PRs, issues, discussions, and other branches remain. Stop other writers while resetting history.")
    if not args.execute:
        print(f"\nPreview only. To reset, add --execute --expected-head {head}")
        return
    if not args.expected_head:
        raise ValueError("Reset requires --expected-head with the full SHA from a fresh preview.")
    with RunLock(state_dir), StateStore(state_dir / "progress.sqlite3") as store:
        result = runner.reset_history(args.expected_head, store)
    print(f"History reset. Backup: {result['backup_branch']}\nNew head: {result['new_sha']}")


def run_wizard(env_file, state_dir, repo=None):
    if not sys.stdin.isatty():
        raise ValueError("Choose an achievement ID for scripted runs, or open the interactive menu in a terminal.")
    console = Console()
    workflow = console.choose("01 / Choose your achievement", [
        Choice(a.slug, a.name, "Helper account" if a.helper else "Solo workflow")
        for a in ACHIEVEMENTS.values()
    ] + [Choice("back", "Back")])
    if workflow == "back":
        return 0
    achievement = ACHIEVEMENTS[workflow]
    choices = [Choice(tier, tier.title(), f"{achievement.thresholds[index]} total recorded successes")
               for tier, index in TIERS.items() if index < len(achievement.thresholds)]
    target = console.choose("02 / Choose your target", choices + [Choice("custom", "Custom count", "New operations"), Choice("back", "Back")])
    if target == "back":
        return 0
    amount = ["--tier", target]
    if target == "custom":
        def validate_count(value):
            if not value.isdigit() or int(value) < 1:
                raise ValueError("Enter a positive whole number.")
        amount = ["--count", console.ask("New operations", "1", validator=validate_count)]
    config = Config.load(env_file, repo=repo)
    if not config.repo:
        config = setup(config, env_file, workflow)
    common = ["--env-file", str(env_file), "--state-dir", str(state_dir), "--repo", config.repo]
    command = common + ["run", workflow, *amount]
    preview = build_parser().parse_args(command)
    show_plan(preview, config)
    action = console.choose("03 / Ready when you are", [
        Choice("execute", "Run this workflow", "Verify prerequisites, perform operations, check badge visibility"),
        Choice("preview", "Keep as preview", "No GitHub changes"),
        Choice("back", "Back"),
    ])
    if action == "execute":
        return main(command + ["--execute"])
    console.say("Preview only. Your plan has not been executed.", "muted")
    return 0


def interactive(env_file, state_dir, repo):
    if not sys.stdin.isatty():
        build_parser().print_help()
        return 0
    console = Console()
    common = ["--env-file", str(env_file), "--state-dir", str(state_dir)]
    if repo:
        common.extend(["--repo", repo])
    while True:
        config = Config.load(env_file, repo=repo)
        summary = []
        if (state_dir / "progress.sqlite3").exists():
            with StateStore(state_dir / "progress.sqlite3") as store:
                summary = store.summary(repo=config.repo)
        completed = sum(row["count"] for row in summary if row["status"] == "completed")
        pending = sum(row["count"] for row in summary if row["status"] != "completed")
        console.banner(config.repo, completed, pending, bool(config.token))
        choice = console.choose("YOUR NEXT MOVE", [
            Choice("run", "Unlock an achievement", "Choose a badge and target tier"),
            Choice("verify", "Check GitHub badges", "Read your public profile"),
            Choice("status", "Your progress", "Completed operations and anything to inspect"),
            Choice("list", "Browse achievements", "Requirements and tiers"),
            Choice("setup", "Connect or create a repository", "Account and repository setup"),
            Choice("doctor", "Check connection", "Validate account and repository access"),
            Choice("reset-history", "Preview history reset", "Preserve files and a backup branch"),
            Choice("back", "Exit"),
        ])
        if choice == "back":
            return 0
        if choice == "run":
            try:
                run_wizard(env_file, state_dir, repo)
            except ValueError as exc:
                console.say(config.redact(str(exc)), "gold")
        elif choice == "status":
            main(common + ["status", "--history"])
        elif choice == "setup":
            section = console.choose("ACCOUNT SETTINGS", [
                Choice("primary", "Primary account and repository"),
                Choice("pair-extraordinaire", "Pair Extraordinaire helper", "Configure or replace its token"),
                Choice("yolo", "YOLO helper", "Collaborator token"),
                Choice("galaxy-brain", "Galaxy Brain helper", "Collaborator token"),
                Choice("back", "Back"),
            ])
            if section != "back":
                main(common + ["setup"] + ([] if section == "primary" else ["--workflow", section]))
        elif choice == "verify" and not config.repo:
            account = console.ask("GitHub username", required=True)
            main(common + ["verify", "--account", account])
        else:
            main(common + [choice])
        input("\n  Press Enter to return to your dashboard...")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    env_file = getattr(args, "env_file", Path(".env"))
    state_dir = getattr(args, "state_dir", Path(".achievement-state"))
    repo = getattr(args, "repo", None)
    config = Config()
    try:
        if args.command is None:
            return interactive(env_file, state_dir, repo)
        if args.command == "list":
            list_achievements(args.json)
            return 0
        config = Config.load(env_file, repo=repo)
        if args.command == "setup":
            setup(config, env_file, args.workflow)
        elif args.command == "status":
            show_status(args, config, state_dir)
        elif args.command == "verify":
            return verify_badges(args, config)
        elif args.command == "doctor":
            if not args.json:
                config = ensure_credentials(config, env_file, args.workflow, allow_create=False)
            config.validate(args.workflow, credentials=True)
            info = make_runner(config).preflight(args.workflow)
            print(json.dumps(info, indent=2) if args.json else
                  f"Connected as {info['account']} to {info['repo']}. Default branch: {info['default_branch']}.")
            if not args.json:
                print("Read-only checks passed. Branch rules and exact write permissions are enforced by GitHub when executing.")
        elif args.command == "run":
            if args.achievement is None:
                if (args.execute or args.dry_run or args.count is not None or args.tier
                        or args.coauthor_name or args.coauthor_email or args.category_id
                        or args.wait_for_badge or args.skip_badge_check or args.interval != 10):
                    raise ValueError("Specify an achievement ID when using run options; use plain run for the interactive chooser.")
                return run_wizard(env_file, state_dir, repo)
            overrides = {key: getattr(args, arg) for key, arg in (
                ("coauthor_name", "coauthor_name"), ("coauthor_email", "coauthor_email"), ("category_id", "category_id")
            ) if getattr(args, arg) is not None}
            config = replace(config, **overrides)
            if args.execute:
                config = ensure_credentials(config, env_file, args.achievement)
            execute_run(args, config, state_dir)
        elif args.command == "reset-history":
            reset_history(args, config, state_dir)
        return 0
    except (ValueError, GitHubError, OSError, sqlite3.Error) as exc:
        print("Error: " + config.redact(str(exc)), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Any started operation is recorded in the local journal.", file=sys.stderr)
        return 130
