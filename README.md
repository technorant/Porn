# GitHub Achievement Python

A guided terminal app for GitHub achievement workflows, with live progress and public badge checks.

Five achievement workflows, an interactive menu, scriptable commands, and a durable local progress journal. Runs on Python 3.11+ with **no third-party runtime dependencies**. No Git installation or local repository clone is needed to operate on a target repository.

## Clone and run

Install [Python 3.11 or newer](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads). Python's installer includes pip on Windows and macOS; Linux distributions may provide pip and venv as separate packages. Confirm Python is available with `python --version` (Windows) or `python3 --version` (macOS/Linux).

After this project is published to GitHub, replace `YOUR_USERNAME` in the clone URL with the account hosting **this CLI's source code**. This is separate from the achievement repository you choose inside the app. If you publish it under a different repository name, adjust the URL and directory below.

### Windows / PowerShell

```powershell
git clone https://github.com/YOUR_USERNAME/github-achievement-python.git
cd github-achievement-python
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m github_achievement
```

### macOS / Linux

```bash
git clone https://github.com/YOUR_USERNAME/github-achievement-python.git
cd github-achievement-python
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m github_achievement
```

No activation step is needed when using the virtual environment's Python directly. `requirements.txt` documents that this app has no third-party runtime packages, so installing it may produce no package downloads. Python and Git are system prerequisites, not pip dependencies.

Each person using the app supplies **their own GitHub tokens** through the hidden prompts. Choose **Connect or create a repository** to start, or select an achievement and follow its setup. Pair Extraordinaire asks for a token from the second account. Personal tokens, `.env`, and local progress are not distributed with the source.

If Git is unavailable, download this project's ZIP from GitHub, extract it, open a terminal in the extracted folder, and follow the commands above starting with virtual environment creation.

## Start

From this project's directory:

```powershell
python -m github_achievement list
python -m github_achievement run pull-shark --repo YOUR_USERNAME/achievement-lab --tier base
```

The second command previews a plan. It needs no token, performs no network requests, and creates no progress database. Add `--execute` when you want the listed operations performed on GitHub.

For the interactive dashboard:

```powershell
python -m github_achievement
```

Use **Up/Down**, **j/k**, or number keys to select an action; **Enter** confirms and **Esc** goes back. Choose an achievement, select a tier or custom count, then review and run the plan. The dashboard shows completed operations and records that need inspection. Colored panels, a live spinner, operation stages, and progress bars keep long runs visible. `NO_COLOR` disables colors; simple numbered menus work in basic terminals.

The remaining examples use `python`; substitute `.venv\Scripts\python` on Windows or `.venv/bin/python` on macOS/Linux if you followed the virtual environment setup above.

Optionally install the command into a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\github-achievement list
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/github-achievement`. Installation needs setuptools as a build dependency; running the module directly does not need pip or downloaded packages.

## Configure

Setup can use an existing personal repository or create one on your account. Choose **Create a repository**, enter its name, and select public or private visibility. The new repository starts with a README and Issues enabled. Creating a repository requires a token with repository-creation permission; a classic `repo` token works. For an existing repository, initialize it with a commit and enable merge commits for PR workflows. The CLI discovers its default branch.

```powershell
python -m github_achievement setup
```

The wizard hides tokens and saves them in a local `.env`. Basic setup asks only for the primary token. Selecting Pair Extraordinaire, YOLO, or Galaxy Brain asks for a helper token if one is not already configured. You can also use `setup --workflow pair-extraordinaire` to configure it directly. Alternatively, copy `.env.example` to `.env` or set environment variables:

```powershell
$env:GITHUB_TOKEN = 'YOUR_PRIMARY_TOKEN'
$env:TARGET_REPO = 'YOUR_USERNAME/achievement-lab'
python -m github_achievement doctor
```

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | Primary personal access token; `GH_TOKEN` is also accepted |
| `TARGET_REPO` | `OWNER/REPO`; overridden by `--repo` |
| `HELPER_TOKEN` | A different account, required for Pair Extraordinaire, YOLO, and Galaxy Brain |
| `COAUTHOR_NAME` | Optional Pair Extraordinaire name override; defaults to the helper's profile name |
| `COAUTHOR_EMAIL` | Optional helper email override; defaults to its GitHub noreply address |
| `DISCUSSION_CATEGORY_ID` | Optional GraphQL node ID for an answerable category |

Shell values override `.env`; an exported `GH_TOKEN` also overrides a primary token in the file. The env parser reads literal values and does not execute or interpolate shell expressions. Remove optional values directly from `.env` to clear them. Configured helper tokens are reused, and blank primary-token prompts keep the configured value.

`.env` contains plaintext credentials and is gitignored. POSIX file permissions are restricted to the owner; on Windows, access follows your directory's permissions. Tokens are never included in the journal or normal output.

### Token and repository permissions

For the primary account, use a fine-grained token restricted to the target repository, with the permissions needed by your selected workflow:

| Workflow | Primary token | Helper token / setup |
| --- | --- | --- |
| Pull Shark | Contents: read/write; Pull requests: read/write | No helper |
| Pair Extraordinaire | Contents: read/write; Pull requests: read/write | Helper token with authenticated profile access; no repository write access needed |
| Quickdraw | Issues: read/write | Enable Issues |
| YOLO | Contents: read/write; Pull requests: read/write | Helper: classic PAT with `repo` scope; accepted collaborator invitation |
| Galaxy Brain | Discussions: read/write | Helper: classic PAT with `repo` scope; accepted collaborator invitation; enable Discussions with Q&A or another answerable category |
| History reset | Contents: read/write | Default branch must permit the force update |

GitHub automatically includes metadata read access. A classic `repo` token is also an alternative for the primary account with broader access. For YOLO and Galaxy Brain, the helper needs a classic token because [GitHub currently limits fine-grained tokens for repository collaborators](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens-limitations).

Pair Extraordinaire verifies the helper's identity, rejects the primary account as its own helper, and derives a private GitHub noreply address. Before opening the PR, it checks that GitHub's commit-author data recognizes both accounts. A custom `COAUTHOR_EMAIL` must match a verified helper email (requiring helper `user:email` access), or the helper's GitHub noreply address. If attribution does not resolve, execution stops with the branch preserved. The helper's name and email are not enough on their own: this workflow requires its token.

Repository rules and token restrictions still apply; the CLI does not change them. Use `doctor --workflow ACHIEVEMENT` to check ownership, helper identity, enabled features, and relevant repository settings before executing. Read checks cannot prove every write is permitted.

## Workflows

| ID | Base / Bronze / Silver / Gold | Behavior |
| --- | --- | --- |
| `pull-shark` | 2 / 16 / 128 / 1024 | Create and merge pull requests |
| `pair-extraordinaire` | 1 / 10 / 24 / 48 | Merge PRs containing co-authored commits |
| `quickdraw` | 1 | Open and close an issue within five minutes |
| `yolo` | 1 | Have the helper account merge a primary-account PR without requesting a review |
| `galaxy-brain` | 2 / 8 / 16 / 32 | Helper asks a question, primary answers, helper accepts the answer |

Thresholds follow community reports. GitHub controls badge eligibility and award timing; successful API operations do not guarantee a badge. Badge requirements can change. Private-repository visibility settings may also affect what your profile shows.

Examples (omit `--execute` to preview any `run` command):

```powershell
python -m github_achievement run pull-shark --tier base --execute
python -m github_achievement run pair-extraordinaire --tier base --execute
python -m github_achievement run quickdraw --execute
python -m github_achievement run yolo --execute
python -m github_achievement run galaxy-brain --tier base --execute
```

`--count N` always schedules N **new** operations. `--tier base|bronze|silver|gold` runs only the number still needed according to successful local records for the authenticated account, repository, and selected workflow. The two options are mutually exclusive. Quickdraw and YOLO only have a base tier. Without either option, one new operation is scheduled.

PR workflows update `.github-achievements/<workflow>.json`, create a unique branch, wait for GitHub to calculate mergeability, and merge with a pinned head SHA. They preserve co-author trailers and delete only their own successfully merged branches. README files are not modified. Merges and closed issues are verified with a separate read; accepted answers are checked against the primary account. YOLO also checks for reviews and verifies the helper performed the merge. GitHub may award multiple badges for one PR; local counts track only the selected workflow.

## Verify badges on GitHub

Successful runs check the public profile once. To allow time for GitHub to display the badge, use `--wait-for-badge 120`. Waiting only reads the profile; it never creates more contributions. Use `--skip-badge-check` to verify API operations only.

```powershell
python -m github_achievement verify --account YOUR_USERNAME
python -m github_achievement verify --account YOUR_USERNAME --achievement pair-extraordinaire --wait 120
python -m github_achievement verify --account YOUR_USERNAME --json
```

The badge checker reports **visible**, **not visible yet**, or **unknown**. It reads actual badge elements on the public profile, excluding README content, and never sends tokens to the GitHub website. A badge that is hidden or delayed cannot be distinguished from one that has not been awarded. Unrecognized page markup and connection failures report unknown. This is a best-effort public-page check, not an official achievements API; badge tier levels and newly-awarded status are not inferred. Profile polling is bounded to 600 seconds at 15-second intervals. The `verify` command exits with 3 when any requested badge cannot be confirmed.

## Progress and failures

```powershell
python -m github_achievement status
python -m github_achievement status --history
python -m github_achievement status --account YOUR_USERNAME --json
```

Progress is stored in `.achievement-state/progress.sqlite3`, scoped to account and repository. Keep this directory between runs. `status` is offline and reports local operations, **not badges fetched from GitHub**. Use `--state-dir PATH` for a stable location when running from different directories.

Each operation records its stage and available resource URLs, branch names, or IDs. Execution stops on failure. Failed and interrupted operations are not counted or automatically replayed. Inspect `status --history` and the recorded GitHub resources before starting another operation: a network timeout may happen after a remote write succeeded. A hard process termination leaves a `running` record for inspection. There is no automatic reconciliation of those records or partial-operation resume.

Cleanup failures after a confirmed merge are recorded as warnings, and the successful merge is still counted. Partial failed PR workflows keep their branch and PR for inspection. An OS lock prevents simultaneous runs sharing the same state directory; use one state directory for a target and avoid concurrent runs from other machines.

REST and GraphQL writes share a serial eight-second minimum spacing. There is also a configurable pause between operations (`--interval`, default 10 seconds). Read failures and explicit rate-limit rejections receive bounded retries; ambiguous write failures do not. Server-requested waits over 60 seconds stop the run with a retry hint.

## History reset

This optional command rewrites the default branch to one root commit while keeping its current files. It preserves the old head on a unique `achievement-backup/<operation-id>` branch. It does not delete PRs, issues, discussions, other branches, or the repository.

```powershell
# Read-only preview; requires authentication.
python -m github_achievement reset-history

# Substitute the full SHA printed by a fresh preview.
python -m github_achievement reset-history --execute --expected-head FULL_SHA_FROM_PREVIEW
```

Stop other writers first. The CLI checks the head again immediately before updating it, but GitHub's force-update endpoint does not offer an atomic expected-old-SHA check, so an external push in that final interval can race the reset. Branch rules may reject it. The backup is recorded before the update, including on failure; keep it until you have checked the result. Old history remains reachable through that backup branch.

## Commands

```text
list [--json]
setup [--workflow ID]
doctor [--workflow ID] [--json]
status [--account LOGIN] [--history] [--limit N] [--json]
verify [--account LOGIN] [--achievement ID] [--wait SECONDS] [--json]
run ID [--count N | --tier TIER] [--execute | --dry-run] [--interval SECONDS]
reset-history [--execute --expected-head SHA]
```

All commands accept `--repo`, `--env-file`, and `--state-dir` before or after the command. Use `run` without an ID to open the workflow chooser. `--help` describes additional options. Exit codes: 0 success/preview, 1 operational/configuration error, 2 argument error, 3 badge not confirmed by `verify`, 130 interruption. A successful `run` means the operations passed verification; read its separate badge report for award visibility.

## Development

```powershell
python -m unittest discover -s tests -v
```

The tests use simulated GitHub responses and never create live resources. They cover all five workflows, authentication boundaries, co-author attribution, merge verification, request pacing, rate limits, failed and interrupted writes, progress persistence, keyboard menus, conditional credential prompts, repository creation, badge parsing and polling, preview behavior, and history backups. CI runs the suite on Windows and Linux, Python 3.11 and 3.14.

The interface is in English. Live GitHub integration and actual badge awards require configured accounts and a repository. Local tests cannot establish that GitHub has awarded a badge.

## License

See [LICENSE](LICENSE).
