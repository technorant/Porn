# Advanced options

For the shortest setup, use the numbered steps in [README.md](README.md).

## Use a token limited to one repository

1. Open [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens).
2. Generate a token. Set the resource owner to your account, set an expiration, and select **Only select repositories**.
3. Choose the test repository and grant the permissions below for the workflows you need.
4. Generate the token and save it as `GITHUB_TOKEN` in `.env`.

| Workflow | Repository permissions |
| --- | --- |
| Pull Shark, Pair Extraordinaire, YOLO | Contents: read/write; Pull requests: read/write |
| Quickdraw | Issues: read/write |
| Galaxy Brain | Discussions: read/write |
| Cleanup | Contents: read/write; Pull requests: read |
| History reset | Contents: read/write; repository must allow the force update |

Metadata read access is included automatically. For helper writes to another user's personal repository, use a classic `repo` token because fine-grained tokens have collaborator limitations. See [GitHub's token documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

## Environment precedence

The app reads `.env` in the current folder. Shell variables override that file. `--repo` overrides `TARGET_REPO`; `--env-file PATH` selects another env file.

If an old shell token is overriding `.env`, clear only these process variables before rerunning.

PowerShell:

```powershell
Remove-Item Env:GITHUB_TOKEN, Env:GH_TOKEN, Env:HELPER_TOKEN, Env:TARGET_REPO -ErrorAction SilentlyContinue
```

macOS/Linux:

```bash
unset GITHUB_TOKEN GH_TOKEN HELPER_TOKEN TARGET_REPO
```

This removes the values from the current shell, not from `.env` or your GitHub account. Tokens are never included in the operation journal.

## Co-author email options

Pair Extraordinaire normally uses the helper's GitHub noreply email and profile name. To override them, add:

```dotenv
COAUTHOR_NAME=Your collaborator's name
COAUTHOR_EMAIL=their-verified-email@example.com
```

A custom email must belong to the helper account and be verified. Give the helper token **user:email** access so the app can check it. The helper's GitHub noreply email is also supported. The app waits briefly for GitHub to recognize both commit authors and stops before merging if they are not recognized.

## Targets and progress

`--count N` creates N new operations. `--tier` uses completed local records and runs only what is still needed for that target. They cannot be combined.

| Badge | Base | Bronze | Silver | Gold |
| --- | --- | --- | --- | --- |
| Pull Shark | 2 | 16 | 128 | 1024 |
| Pair Extraordinaire | 1 | 10 | 24 | 48 |
| Galaxy Brain | 2 | 8 | 16 | 32 |
| Quickdraw | 1 | — | — | — |
| YOLO | 1 | — | — | — |

These are community-reported thresholds, not guarantees of badge awards. Counts are scoped to the authenticated account, target repository and selected workflow. An operation may trigger other badges on GitHub, but the app counts it only under the selected workflow.

Keep `.achievement-state/progress.sqlite3` between runs. Use `--state-dir PATH` to choose another location. A failed/interrupted operation is not automatically replayed. Inspect its recorded PR, issue, or discussion before starting a new operation: GitHub may have completed a write even if its response was lost. Cleanup updates branch-cleanup details without changing success counts.

## Message options

Pull Shark, Pair Extraordinaire, and YOLO automatically read the five [predefined message files](README.md#predefined-pr-and-commit-messages). There is no message-entry prompt. The bundled files work when running from source or installing the Python package.

To keep your own files in a separate folder, copy all five `.txt` files from `github_achievement/message_files/` to that folder, then optionally set:

```dotenv
MESSAGES_DIR=my-messages
```

Relative paths are resolved beside the selected `.env` file, not against the current working directory. Absolute paths also work. Leave `MESSAGES_DIR` empty for the included files. Each file needs at least one nonblank, noncomment message line. A missing, empty, or invalid file stops the run with its filename; an invalid entry also reports its entry number.

Messages are selected in file order using the number of recorded attempts for the authenticated account, repository, and workflow. Failed and interrupted attempts also advance the position. Existing operations from older app versions count toward that position. Each file cycles independently when it reaches the end. Keep `.achievement-state` to preserve the position; editing a file's entry count or order changes future selections. File contents are loaded and checked during preflight, then reused throughout that run.

Optional single-template overrides remain available for existing scripts. They replace selection from the corresponding file only; other fields still use their files:

| `.env` setting | Command option | Changes |
| --- | --- | --- |
| `PR_TITLE` | `--pr-title` | Pull request title |
| `PR_BODY` | `--pr-body` | Pull request description |
| `COMMIT_MESSAGE` | `--commit-message` | Activity-file commit message |
| `MERGE_TITLE` | `--merge-title` | Merge commit title |
| `MERGE_MESSAGE` | `--merge-message` | Merge commit description |

For example, preview one co-authored PR with a custom title and commit message:

```powershell
python main.py run pair-extraordinaire --count 1 --pr-title "Record {badge} activity together" --commit-message "Save the co-authored activity record"
```

Add `--execute` to run the previewed workflow. Command options override shell variables, which override `.env`; an empty value restores selection from the corresponding message file. Customizations do not change what files the workflow edits. Shared `.env` message settings are ignored for Quickdraw and Galaxy Brain; supplying PR message options directly for those badges is an error.

Templates accept only `{badge}`, `{workflow}`, `{repo}`, and `{path}`. Use `{{` and `}}` for literal braces and `\n` for newlines in descriptions and commit messages. Template expressions do not execute Python or shell code. The full journal operation ID is appended to every field, including across separate runs. The sample ID shown in a preview is replaced at execution.

The app validates every entry in all active message files before writing a branch, including merge text and the resolved Pair co-author trailer. Titles must be single-line and at most 256 UTF-8 bytes; descriptions and commit messages must fit within 65,536 UTF-8 bytes, including automatic metadata. Invalid placeholders, control characters, or manually supplied co-author trailers stop the run. Shorten the template if its expanded text exceeds these limits.

Pair Extraordinaire retains its verified helper credit on the original commit. The PR is merged with a merge commit, preserving that co-authored commit. Custom merge messages also apply when the YOLO helper performs the merge. API pacing, rate-limit handling, and branch cleanup apply as usual.

## API pacing and retries

All clients in a run share serial write pacing. Eight seconds between writes limits this app's write rate, but other apps and website actions can consume the same account's quota. The client honors `Retry-After` and `X-RateLimit-Reset`, notices exhausted quota on successful responses, and handles GraphQL rate errors returned with HTTP 200.

When no retry time is supplied for a secondary limit, waits start at 60 seconds and grow exponentially. Each request permits at most two retries and a maximum individual wait of 300 seconds. Longer waits stop with a retry hint. A GraphQL mutation with partial results, a lost write response, or a write server error is not blindly replayed. Cleanup stops after an API failure instead of continuing through the remaining branches.

References: [GitHub REST limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [GitHub GraphQL limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api).

## Cleanup boundaries

`cleanup` previews; `cleanup --execute` deletes matching branches. It uses the local journal and confirms the PR's author, source repository, branch, head commit and merged state. The branch's current commit must still match. If the journal is missing, the app cannot identify its old branches automatically.

GitHub may delete a merged branch automatically; an already-missing branch counts as clean. Cleanup does not remove activity files, PR records, issues, discussions, backup branches or commit history. GitHub's branch-deletion API has no atomic expected-head guard, so avoid other writers while cleaning up.

## Optional history reset

This is separate from routine cleanup. It replaces the default branch's history with one root commit while preserving its files and the old head on a backup branch.

```powershell
python main.py reset-history
python main.py reset-history --execute --expected-head FULL_SHA_FROM_PREVIEW
```

Use the full SHA printed by a fresh preview and stop other writers first. The app checks the head again before updating it, but the force-update endpoint has no atomic expected-old-SHA check. Branch rules may reject the update. PRs, issues, discussions and other branches remain. Keep the recorded `achievement-backup/...` branch until you have checked the result.

## Other useful commands

```powershell
python main.py list
python main.py setup
python main.py doctor --workflow pair-extraordinaire
python main.py status --history
python main.py cleanup --json
python main.py verify --account YOUR_USERNAME --json
python main.py --help
```

`setup` can create an initialized repository or configure a helper. `doctor` only checks an existing repository. `python -m github_achievement` and an installed `github-achievement` command still work as alternatives to `python main.py`.

Public badge checks report visible, not visible, or unknown. They do not infer tier levels or distinguish a newly awarded badge from one you already had. Hidden badges, delayed awards and changed GitHub markup limit what can be confirmed. `--wait-for-badge 120` waits after a successful run; `--skip-badge-check` skips the public profile check. Neither setting changes contribution counts.

Exit codes: 0 success/preview, 1 configuration/API error, 2 argument error, 3 a requested badge is not confirmed by `verify`, 130 interruption.

## Optional virtual environment and development

Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

There are no third-party runtime packages. Optional `pip install -e .` uses setuptools as its build dependency, declared in `pyproject.toml`.

Run the offline tests with `python -m unittest discover -s tests -v`. Tests simulate GitHub responses; they cannot prove a live badge award. CI is configured for Windows and Linux on Python 3.11 and 3.14.
