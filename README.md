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

### Two accounts, one target repository

**Use one repository owned by your primary account. The helper does not need to create or fork a repository.** For your existing `technorant/test`, keep using that repository for all badges.

| Account | Repository relationship | Token goes in |
| --- | --- | --- |
| Primary account, such as `technorant` | Owns `technorant/test`; the app performs the primary actions as this account | `GITHUB_TOKEN` |
| Helper account, a different GitHub username | Helps in that same repository; needs an accepted invitation for YOLO and Galaxy Brain | `HELPER_TOKEN` |

`TARGET_REPO` stays **`technorant/test`** for both accounts. Run the CLI once on your computer with both tokens in the same local `.env`; the app switches between them for the required actions. The helper does not need to run a separate copy of the CLI. The two tokens must belong to different accounts.

If you do not have a target repository yet, sign in as your **primary account**, open [Create a repository](https://github.com/new), choose that account as the owner, enter a repository name, and initialize it with a README. Put the resulting `owner/name` in `TARGET_REPO`. One target is enough for all five badges; enable Issues or Discussions when the chosen badge needs them.

**A token belongs to an account, not to an invitation.** Create each token from that account's personal settings. A classic token with `repo` scope can use repository access that its account already has; it cannot grant access by itself. For YOLO and Galaxy Brain, the accepted invitation gives the helper access to the primary account's repository, and the helper's token lets the CLI use that access. Classic token creation does not ask you to select a particular repository.

If the helper has already accepted the invitation to `technorant/test`, that part is done. Keep the same target and create or reuse the helper's own token. A working classic `repo` token can be created before or after accepting the invitation; accepting it alone does not require a new token. Forking creates a separate repository and is not part of this app's helper setup.

### Where to create both tokens

**The main account and helper account use the same procedure. Both tokens are created in personal account settings, never in repository settings.** The only differences are which account you sign in to and which `.env` line receives its token.

Open **[Personal access tokens](https://github.com/settings/tokens)** while signed in to the correct account. To get there through GitHub's menus, use **Profile picture → Settings → Developer settings → Personal access tokens → Tokens (classic)**.

If you see **“You don't have access to repository options”**, you are on a repository settings page, such as `github.com/technorant/test/settings`. That message is expected for a helper without admin access. Open the personal token settings link above instead. The helper does not need admin access, a new repository, or a fork to create its token.

### How to create the primary token

If the main account already has a working classic token with **repo** selected, reuse it.

1. Sign in to your **main GitHub account**—the account that owns the target repository, such as **technorant**.
2. Open **[Personal access tokens](https://github.com/settings/tokens)**.
3. Click **Generate new token → Generate new token (classic)**.
4. Enter a name and choose an expiration date.
5. Select the **repo** checkbox.
6. Click **Generate token** and copy the token.
7. Paste it after **`GITHUB_TOKEN=`** in your local `.env`, then save.

### How to create the helper token

Do this only for **Pair Extraordinaire, YOLO, or Galaxy Brain**. If the second account already has a working classic token with **repo** selected, reuse it.

1. Sign in to your **second GitHub account**—the helper. Check the username under the profile picture to make sure it is different from the main account.
2. Open **[Personal access tokens](https://github.com/settings/tokens)**.
3. Click **Generate new token → Generate new token (classic)**.
4. Enter a name and choose an expiration date.
5. Select the **repo** checkbox.
6. Click **Generate token** and copy the token.
7. Paste it after **`HELPER_TOKEN=`** in your local `.env`, then save.

Keep the main account's token in `GITHUB_TOKEN`. Keep `TARGET_REPO` set to the main account's repository. For `technorant/test`, your file should look like this:

```dotenv
GITHUB_TOKEN=TOKEN_FROM_TECHNORANT
TARGET_REPO=technorant/test
HELPER_TOKEN=TOKEN_FROM_SECOND_ACCOUNT
```

Replace the token placeholders locally with the tokens you copied. For Pull Shark or Quickdraw, leave `HELPER_TOKEN=` empty. Both tokens are used by the same local CLI; do not create a second repository for the helper.

For **YOLO and Galaxy Brain**, the helper must also accept the invitation to that same repository. If it already accepted, keep that access—no new invitation or replacement token is needed. Use the main account to manage invitations and enable Discussions/Q&A. Token creation itself always uses each account's personal settings.

### Which token does each badge need?

**The classic `repo` tokens created above cover every badge in this guide.** Reuse the primary token for all five badges and the helper token for all three helper workflows. A second token from the main account does not count as a helper.

| Badge | Helper token | Must the helper accept a repository invitation? |
| --- | --- | --- |
| Pull Shark | Not needed | No |
| Quickdraw | Not needed | No |
| Pair Extraordinaire | Required; the helper token created above works | No |
| YOLO | Required; classic token with **repo** selected | Yes |
| Galaxy Brain | Required; classic token with **repo** selected | Yes |

The **repo** scope also gives a token access to other repositories its account can access. If you only need **Pair Extraordinaire** with the default co-author settings, a classic helper token with no scopes selected is sufficient. A custom `COAUTHOR_EMAIL` requires **user:email** access on the helper token so the app can verify it; see [co-author email options](ADVANCED.md#co-author-email-options).

For a primary token limited to one repository, see the optional [fine-grained token steps](ADVANCED.md#use-a-token-limited-to-one-repository). Keep using a classic helper token for YOLO and Galaxy Brain because fine-grained tokens have limitations when accessing another personal account's repository. If a required helper token is missing, the CLI asks for it with hidden input.

### What does the helper do for each badge?

| Badge | Primary account's actions | Helper account's actions in this app |
| --- | --- | --- |
| Pair Extraordinaire | Creates the co-authored commit, opens the PR, verifies both authors, and merges it in the primary repository | Supplies its verified account identity for the co-author credit; does not post or merge anything |
| YOLO | Creates the commit and opens the PR in the primary repository | Merges that same PR without a review; needs accepted collaborator access |
| Galaxy Brain | Answers questions in the primary repository's Q&A Discussions | Posts questions there and marks the primary account's replies as accepted answers; needs accepted collaborator access |

Pull Shark and Quickdraw use only the primary account. The same primary token can be kept in `.env` when changing badges.

Never share or commit `.env`. Each person running this app uses their own tokens. The app reads `.env` automatically; you do not need to paste tokens into commands.

PR titles, descriptions, and commit messages are selected automatically from the included [message files](#predefined-pr-and-commit-messages). You do not need to type messages or add message settings to `.env`.

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

After completing Steps 1 and 2, choose either option below. Both use the tokens and repository saved in `.env`.

### Option 1: Run a command

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

### Option 2: Use the interactive CLI

Start the menu from the project folder:

```powershell
python main.py
```

On Windows, if you use the project's virtual environment:

```powershell
.venv\Scripts\python main.py
```

Use **Up/Down** to highlight an option and **Enter** to select it. You can also press its number. **Esc** goes back.

1. Check that the dashboard shows your repository, such as **technorant/test**.
2. Select **Unlock an achievement**.
3. Select **Pull Shark** for the PR test, or choose another badge.
4. Select **Base** to reach the first target using saved progress. To create exactly one new PR instead, select **Custom count** and enter **1**.
5. Read the plan and message preview, then select **Run this workflow**. PR messages are selected automatically from the included text files. Select **Keep as preview** if you only want to see the plan.
6. If the selected badge needs a helper and `HELPER_TOKEN` is missing, enter the second account's token when prompted. Input stays hidden. Pull Shark does not need a helper.
7. Wait for the progress display to finish, then press **Enter** to return to the dashboard.

From the dashboard, select **Your progress** to see completed operations or **Check GitHub badges** to check your public profile. For leftover branches, select **Clean up merged branches**, read the preview, then select **Remove verified merged branches**.

### Predefined PR and commit messages

**Messages are ready to use. No typing or extra setup is needed.** Pull Shark, Pair Extraordinaire, and YOLO automatically select their messages from these files:

| File | Used for |
| --- | --- |
| [prtitle.txt](github_achievement/message_files/prtitle.txt) | PR titles |
| [prdescription.txt](github_achievement/message_files/prdescription.txt) | PR descriptions |
| [messages.txt](github_achievement/message_files/messages.txt) | Activity commit messages |
| [mergetitle.txt](github_achievement/message_files/mergetitle.txt) | Merge commit titles |
| [mergedescription.txt](github_achievement/message_files/mergedescription.txt) | Merge commit descriptions |

Each file contains **12 predefined entries**. The app selects the next entry in each file for each PR, then cycles back to the beginning after the last entry. Saved progress keeps the position across runs, including failed or interrupted attempts. Each account, repository, and badge has its own position.

Every message also includes a unique operation ID. The complete messages stay distinct across 1,024 PRs, while the predefined wording cycles. Pair Extraordinaire automatically gets the verified helper's **Co-authored-by** credit. PR and merge descriptions retain a short automation notice.

**Option 1: Run a command**

After setting up your tokens and repository, run one PR with automatic messages:

```powershell
python main.py run pull-shark --count 1 --execute
```

For Pair Extraordinaire, replace `pull-shark` with `pair-extraordinaire` after setting up its helper. Omit `--execute` to see sample messages without creating a PR. Previews show the first entries with a sample ID; execution selects the next position from your saved progress.

**Option 2: Use the interactive CLI**

1. Run `python main.py`.
2. Select **Unlock an achievement → Pull Shark** (or **Pair Extraordinaire** or **YOLO**), then choose your target.
3. Select **Run this workflow**. The app chooses all five messages automatically.

**Optional: Edit the predefined wording**

The files are inside `github_achievement/message_files/`. If you want different wording later, open the appropriate file, edit or add entries, save it, and start your next run. The app checks every entry before writing to GitHub and keeps the selected files in memory during that run.

Use one message per line. Blank lines and lines beginning with `#` are ignored. Use `\n` inside descriptions or commit messages for a newline; titles must stay on one line. Save files as UTF-8. Do not add co-author trailers yourself.

| Placeholder | Example replacement |
| --- | --- |
| `{badge}` | `Pull Shark` or `Pair Extraordinaire` |
| `{workflow}` | `pull-shark` or `pair-extraordinaire` |
| `{repo}` | `technorant/test` |
| `{path}` | `.github-achievements/pull-shark.json` |

For literal braces, write `{{` and `}}`. If an older `PR_TITLE`, `PR_BODY`, `COMMIT_MESSAGE`, `MERGE_TITLE`, or `MERGE_MESSAGE` setting is overriding a file, remove that message setting from `.env` or your shell. Keep your tokens. See [advanced message options](ADVANCED.md#message-options) for using a separate folder or an explicit override.

## 4. Run another badge

Use **Option 2** above and select the badge you want, or run its command below. Complete the listed prerequisites first. Use one command at a time; `--execute` performs the work, and leaving it out shows a preview.

### Pair Extraordinaire

**Repository:** use the primary account's repository, such as `technorant/test`. The helper does not need its own repository, a fork, or a collaborator invitation for this badge. All GitHub writes use the primary token; the helper token is used to read the co-author's identity.

1. Keep the owner's classic **repo** token in `GITHUB_TOKEN` and that owner's repository in `TARGET_REPO`. Initialize the repository with a README and enable **Allow merge commits** as described in Step 2.
2. Follow [How to create the helper token](#how-to-create-the-helper-token), signing in as the second account. Save its token in `HELPER_TOKEN`. For Pair alone, a classic token with no scopes selected is enough; an existing helper classic **repo** token also works.
3. Leave `COAUTHOR_NAME` and `COAUTHOR_EMAIL` unset unless you need an override. The app gets the helper's identity automatically and checks that GitHub recognizes both commit authors. A custom co-author email must be verified on the helper account, and the helper token needs **user:email** access to check it.
4. Check the setup:

```powershell
python main.py doctor --workflow pair-extraordinaire
```

5. If the check passes, run:

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

**Repository:** both accounts use the primary account's repository, such as `technorant/test`. The primary opens the PR there and the helper merges it there. The helper does not create or fork a repository.

1. Keep the owner's classic **repo** token in `GITHUB_TOKEN` and the owner's repository in `TARGET_REPO`. The repository needs an initial commit and **Allow merge commits** enabled.
2. Follow [How to create the helper token](#how-to-create-the-helper-token). Create a classic token with **repo** selected while signed in as the second account, and save it in `HELPER_TOKEN`.
3. Sign in as the repository owner. Open that same target repository → **Settings → Collaborators** (under **Access**) → **Add people**.
4. Search for the helper's GitHub username, select the correct account, and click **Add NAME to REPOSITORY**.
5. Sign in as the helper, open the invitation from GitHub's email, and accept it. Sending the invitation alone is not enough.
6. As the owner, check **Settings → Collaborators** again: the helper should have access, with no pending invitation. If the helper already accepted an invitation for Galaxy Brain in this repository, skip sending another invitation and reuse that access.
7. Check the setup:

```powershell
python main.py doctor --workflow yolo
```

8. If the check passes, run:

```powershell
python main.py run yolo --tier base --execute
```

The helper merges the PR without a review. Existing branch rules still apply.

### Galaxy Brain

This workflow needs **two different accounts**. The helper posts questions, your primary account answers, and the helper marks those answers as accepted.

**Repository:** all questions and answers go into the primary account's repository, such as `technorant/test`. The helper accepts access to that exact repository. It does not need to create a repository or fork the invited repository. Keep `TARGET_REPO=technorant/test` when configuring either token.

#### A. Save both tokens in `.env`

1. Keep the repository owner's classic token with **repo** selected in `GITHUB_TOKEN`.
2. Sign in to the **helper account** and create its own classic token with **repo** selected using [How to create the helper token](#how-to-create-the-helper-token). This happens in the helper's personal settings, not the repository settings. If you already have a working helper classic **repo** token, reuse it.
3. Put that second token in `HELPER_TOKEN`. Check that `TARGET_REPO` points to your test repository, then save `.env`:

```dotenv
GITHUB_TOKEN=YOUR_REPOSITORY_OWNER_TOKEN
TARGET_REPO=technorant/test
HELPER_TOKEN=YOUR_SECOND_ACCOUNT_TOKEN
```

Replace the placeholders with your tokens locally. Other users should replace `technorant/test` with a repository owned by their primary account. You do not select a repository when creating a classic token: the owner's account already owns the target, and the helper gains access by accepting the invitation in the next step.

#### B. Invite the helper and accept the invitation

1. Sign in as the **repository owner** and open your test repository on GitHub.
2. Open **Settings → Collaborators**, under **Access**. GitHub may ask you to confirm your password.
3. Click **Add people**, search for the helper's GitHub username, and select the correct account.
4. Click **Add NAME to REPOSITORY** to send the invitation.
5. Sign in as the **helper account**, open the invitation from GitHub's email, and accept it. Make sure you accept while signed in to the helper, not the owner.
6. Switch back to the owner and check **Settings → Collaborators**. The helper must appear with access, not as a pending invitation. An accepted collaborator invitation gives the helper write access to a personal repository.

Already accepted the invitation to this same repository, including for YOLO? This step is done. Reuse that access and the helper's own classic **repo** token; accepting an invitation does not require creating a new token. See [GitHub's invitation guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) if you get stuck.

#### C. Enable Discussions and a Q&A category

1. As the owner, open the repository's **Settings → General → Features**.
2. Find **Discussions** and choose **Set up discussions**. Complete the welcome post and click **Start discussion** if prompted. If Discussions is already enabled, open the repository's **Discussions** tab.
3. Look for the **Q&A** category. It must use the **Question and Answer** format, which allows an answer to be accepted.
4. If it is missing, click the edit/pencil icon beside **Categories** → **New category**. Enter a name such as **Q&A**, choose an emoji, add a description, select **Question and Answer**, then click **Create**. If a category named Q&A already exists but uses another format, edit it to use **Question and Answer**.

The app automatically finds a category that supports accepted answers. Leave `DISCUSSION_CATEGORY_ID` unset unless you want to select a specific category. See [GitHub's category guide](https://docs.github.com/en/discussions/managing-discussions-for-your-community/managing-categories-for-discussions) for the category settings.

#### D. Check setup, then run

From a terminal inside the project folder, check the accounts, helper access, and discussion category:

```powershell
python main.py doctor --workflow galaxy-brain
```

Resolve any errors before continuing. `doctor` checks account access and the available Q&A category; it does not post a question or test every write permission. For `Resource not accessible by personal access token`, follow the [token access checklist](#fix-resource-not-accessible-by-personal-access-token). Then choose either way to run:

**Option 1: Run a command**

```powershell
python main.py run galaxy-brain --tier base --execute
```

**Option 2: Use the interactive CLI**

```powershell
python main.py
```

Select **Unlock an achievement → Galaxy Brain → Base → Run this workflow**. Wait for the run to finish, then press **Enter** to return to the dashboard.

The base target is **2 completed accepted-answer operations**. Saved progress counts toward that target, so the app only runs what remains. You can open the resulting discussions on GitHub to check that the primary account's answers are marked as accepted.

To check whether the badge is visible on your primary account's public profile, allowing up to two minutes:

```powershell
python main.py verify --achievement galaxy-brain --wait 120
```

GitHub decides when to award the badge. If it is not visible yet, check again later; completing the workflow does not guarantee an immediate award.

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
| `You don't have access to repository options` | You opened repository settings. Create either account's token in [personal token settings](https://github.com/settings/tokens); helper admin access is not needed. |
| `Resource not accessible by personal access token` | Check both accounts and their access to the same target using the [token access checklist below](#fix-resource-not-accessible-by-personal-access-token). |
| `0 operation(s) to run` | Your saved progress already meets this tier. Use `--count 1` only if you want a new test. |
| PR cannot merge | Check conflicts, required reviews/checks, and **Allow merge commits**. |
| Co-author not recognized | Check the helper account. See [co-author email options](ADVANCED.md#co-author-email-options). |
| `.env` changes seem ignored | An old shell variable can override the file. See [environment precedence](ADVANCED.md#environment-precedence). |
| Badge is not visible | Wait and run `verify` again; do not assume more PRs are needed. |

### Fix `Resource not accessible by personal access token`

This message means a token lacks access to the requested resource or action. Creating a fork does not fix access to the original repository.

1. Check `TARGET_REPO`. For `technorant/test`, `GITHUB_TOKEN` must belong to **technorant**, and `HELPER_TOKEN` must belong to a **different account**. Keep both tokens in the same local `.env`.
2. For **Galaxy Brain or YOLO**, use classic tokens with **repo** selected for both accounts as described in this guide. A helper fine-grained token may not support writing to another personal account's repository, even after accepting its invitation. If using a fine-grained **primary** token, it must select the target repository and have the [permissions for the chosen workflow](ADVANCED.md#use-a-token-limited-to-one-repository).
3. For **Galaxy Brain or YOLO**, open the target's **Settings → Collaborators** as the owner. Confirm that the account which created `HELPER_TOKEN` has accepted its invitation to this exact repository. Access to a fork or to another repository is not sufficient. For **Pair Extraordinaire**, no invitation is required; a failure while checking commit authors concerns the primary token's repository access.
4. For **Galaxy Brain**, enable Discussions and a category using **Question and Answer** format on the target repository itself.
5. Save corrected values in `.env` and restart the CLI. If it still uses an older token, check [shell variables that override `.env`](ADVANCED.md#environment-precedence). Run the matching `doctor --workflow` command from the badge's instructions, then inspect `python main.py status --history` before starting another run if the previous attempt had already created resources.

An accepted invitation and a correctly scoped token are separate requirements. The helper can keep an existing token if it already has the right type and permissions; there is no special token created by accepting an invitation.

## Get the app

Install [Python 3.11+](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads). Replace `SOURCE_REPO_URL` with the GitHub URL where this CLI is published:

```powershell
git clone SOURCE_REPO_URL github-achievement-python
cd github-achievement-python
```

Or download its ZIP from GitHub and extract it. Then start at **Step 1: `.env`** above. The cloned source repository and your `TARGET_REPO` are separate: the first contains this app; the second receives the test PRs.

[Advanced options](ADVANCED.md) · [License](LICENSE)
