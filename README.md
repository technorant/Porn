# GitHub Achievement Python

Run GitHub achievement workflows from a menu or a command.

**Start with `.env`, then run the commands below.** If you have not downloaded the app, use [Get the app](#get-the-app) first. You need Python 3.11 or newer. No extra Python packages are required.

## 1. Put your tokens in `.env`

Open the project folder. Create a file named **`.env`** next to `main.py`, or edit the one you already have. Do not replace an existing working token.

```dotenv
GITHUB_TOKEN=PASTE_YOUR_PRIMARY_TOKEN_HERE
TARGET_REPO=technorant/test
HELPER_TOKEN=
```

Save the file. Use `.env`, not `.env.txt`. These examples use `technorant/test`; other users should put **their own** `username/repository` in `TARGET_REPO`.

### How to create the primary token

If your token already works, skip these steps.

1. Sign in to the GitHub account that owns the test repository.
2. Open [GitHub token settings](https://github.com/settings/tokens).
3. Select **Generate new token → Generate new token (classic)**.
4. Give it a name, choose an expiration date, and select **repo**. This scope covers the workflows in this guide; it also gives access to other repositories that account can access.
5. Select **Generate token** and copy it.
6. Paste it after `GITHUB_TOKEN=` in `.env`, then save.

Prefer a token limited to one repository? Follow the [fine-grained token steps](ADVANCED.md#use-a-token-limited-to-one-repository) instead.

### When do I need a helper token?

| Badge | Helper token needed? |
| --- | --- |
| Pull Shark | No |
| Quickdraw | No |
| Pair Extraordinaire | Yes, from a different account |
| YOLO | Yes, from a different account with repository access |
| Galaxy Brain | Yes, from a different account with repository access |

For a helper, sign in to the **second account**, create its token, and paste it after `HELPER_TOKEN=`. For YOLO or Galaxy Brain, use a classic token with **repo** selected. For Pair Extraordinaire only, authenticated profile access is enough; repository access is not needed. If a required helper token is missing, the CLI asks for it with hidden input.

Never share or commit `.env`. Each person running this app uses their own tokens. The app reads `.env` automatically; you do not need to paste tokens into commands.

## 2. Check the repository and connection

For PR badges, the repository must have at least one commit. If it is empty, add a README on GitHub. Under **Settings → General → Pull Requests**, enable **Allow merge commits**.

Open a terminal **inside this project folder** and run:

```powershell
python -m pip install -r requirements.txt
python main.py doctor
```

You should see `Connected as technorant to technorant/test` when using that account. If Python is called `python3` on your computer, replace `python` with `python3` in the commands.

Already using the project's virtual environment on Windows? Replace `python` with `.venv\Scripts\python`. You do not need to install the app as a package.

## 3. Run your first PR test

To work toward the base Pull Shark badge:

```powershell
python main.py run pull-shark --tier base --execute
```

The base target is **2 completed PR operations**. The app uses its saved progress, so it will not repeat operations already counted toward that target. If you already completed 16 PR operations, this command schedules **0** more.

To create **exactly one new test PR**, use this instead:

```powershell
python main.py run pull-shark --count 1 --execute
```

The app creates a branch, makes a small activity-file change, opens and merges a PR, verifies the merge, and removes the temporary branch. Each operation takes time because API writes are paced.

Prefer the menu? Run `python main.py`, choose **Unlock an achievement**, and follow the prompts. Use arrows or number keys to choose an item.

## 4. Run another badge

Use one command at a time. `--execute` performs the work; leaving it out shows a preview.

### Pair Extraordinaire

1. Put the second account's token in `HELPER_TOKEN` in `.env`.
2. Leave `COAUTHOR_NAME` and `COAUTHOR_EMAIL` unset unless you need an override. The app gets the helper's identity automatically and checks that GitHub recognizes both commit authors.
3. Run:

```powershell
python main.py run pair-extraordinaire --tier base --execute
```

### Quickdraw

1. In your test repository, open **Settings → General → Features** and enable **Issues**.
2. Run:

```powershell
python main.py run quickdraw --tier base --execute
```

This opens and closes an issue within five minutes. No helper is needed.

### YOLO

1. Put the second account's classic token with **repo** scope in `HELPER_TOKEN`.
2. In the test repository, open **Settings → Collaborators**, invite that account, and accept the invitation while signed in to it.
3. Run:

```powershell
python main.py run yolo --tier base --execute
```

The helper merges the PR without a review. Existing branch rules still apply.

### Galaxy Brain

1. Set up the helper token and collaborator access using the YOLO steps above.
2. In the repository, open **Settings → General → Features** and enable **Discussions**. Make sure it has a **Q&A** category that supports accepted answers.
3. Run:

```powershell
python main.py run galaxy-brain --tier base --execute
```

The helper posts questions, the primary account answers, and the helper accepts those answers.

## 5. Check progress and badges

```powershell
python main.py status
python main.py verify
```

`status` shows this app's completed operations. `verify` checks badges visible on the public profile. GitHub decides when to award badges; a completed operation is not proof of an award. Hidden or delayed badges may show **not visible yet**.

To allow two minutes for a badge to appear, without creating more activity:

```powershell
python main.py verify --achievement pull-shark --wait 120
```

Keep the `.achievement-state` folder. It holds progress for each account and repository. Do not delete it to retry a failed run. For failure details, use `python main.py status --history`.

## 6. Clean up leftover branches

Successfully merged workflow branches are removed automatically. If a cleanup failed or a run was interrupted, check for leftovers:

```powershell
python main.py cleanup
```

This is a preview. To remove branches marked **READY**:

```powershell
python main.py cleanup --execute
```

Cleanup only removes recorded workflow branches whose PR is merged and whose commit has not changed. Unmerged PRs, unknown branches, backup branches, files, and repository history are kept. **KEPT** means inspect that branch manually. Cleanup does not erase your local progress or create more PRs.

Run one copy of the app at a time and avoid editing its temporary branches while it runs.

## Rate limits: let the app wait

The app spaces API writes eight seconds apart and adds a pause between operations. It reads GitHub's rate-limit headers and waits when instructed. A secondary limit with no retry time gets a wait of at least 60 seconds; repeated limits get longer waits. REST and GraphQL limits are handled.

If GitHub asks for a wait longer than five minutes, or retries are exhausted, the run stops and shows when to retry. Completed progress stays saved. Do not restart repeatedly to bypass the wait. If the limit happened during branch cleanup, run `python main.py cleanup --execute` after the wait.

## Common fixes

| Message or problem | What to do |
| --- | --- |
| `401` / invalid token | Replace an expired or incorrect token in `.env`. |
| `403` / `404` | Check the repository name, token permissions, and helper invitation. |
| `0 operation(s) to run` | Your saved progress already meets this tier. Use `--count 1` only if you want a new test. |
| PR cannot merge | Check conflicts, required reviews/checks, and **Allow merge commits**. |
| Co-author not recognized | Check the helper account. See [co-author email options](ADVANCED.md#co-author-email-options). |
| `.env` changes seem ignored | An old shell variable can override the file. See [environment precedence](ADVANCED.md#environment-precedence). |
| Badge is not visible | Wait and run `verify` again; do not assume more PRs are needed. |

## Get the app

Install [Python 3.11+](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads). Replace `SOURCE_REPO_URL` with the GitHub URL where this CLI is published:

```powershell
git clone SOURCE_REPO_URL github-achievement-python
cd github-achievement-python
```

Or download its ZIP from GitHub and extract it. Then start at **Step 1: `.env`** above. The cloned source repository and your `TARGET_REPO` are separate: the first contains this app; the second receives the test PRs.

[Advanced options](ADVANCED.md) · [License](LICENSE)
