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

### Which token does each badge need?

**One primary token works for all five badges:** use a **Personal access token (classic)** with **repo** selected, saved as `GITHUB_TOKEN`. You do not need to create a new primary token for each badge.

Some badges also need a token from a **different GitHub account**, saved as `HELPER_TOKEN`:

| Badge | Helper token | Must the helper accept a repository invitation? |
| --- | --- | --- |
| Pull Shark | Not needed | No |
| Quickdraw | Not needed | No |
| Pair Extraordinaire | Required; classic token with profile access is enough | No |
| YOLO | Required; classic token with **repo** selected | Yes |
| Galaxy Brain | Required; classic token with **repo** selected | Yes |

To create a helper token, sign in to the **second account** and follow the [token creation steps above](#how-to-create-the-primary-token). Paste the result after `HELPER_TOKEN=`, leaving `GITHUB_TOKEN` unchanged. You can reuse the same helper classic **repo** token for Pair Extraordinaire, YOLO, and Galaxy Brain. A second token from your primary account does not count as a helper.

For **Pair Extraordinaire only**, a classic helper token with no scopes selected is sufficient when using the default co-author settings; no repository invitation is needed. If you set a custom `COAUTHOR_EMAIL`, also select **user:email** on the helper token so the app can verify it. See [co-author email options](ADVANCED.md#co-author-email-options).

For **YOLO and Galaxy Brain**, the helper must accept the invitation before running. Use a classic helper token because fine-grained tokens have limitations when accessing another personal account's repository. If a required helper token is missing, the CLI asks for it with hidden input.

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
5. Read the plan, then select **Run this workflow**. Select **Keep as preview** if you only want to see the plan.
6. If the selected badge needs a helper and `HELPER_TOKEN` is missing, enter the second account's token when prompted. Input stays hidden. Pull Shark does not need a helper.
7. Wait for the progress display to finish, then press **Enter** to return to the dashboard.

From the dashboard, select **Your progress** to see completed operations or **Check GitHub badges** to check your public profile. For leftover branches, select **Clean up merged branches**, read the preview, then select **Remove verified merged branches**.

## 4. Run another badge

Use **Option 2** above and select the badge you want, or run its command below. Complete the listed prerequisites first. Use one command at a time; `--execute` performs the work, and leaving it out shows a preview.

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
2. Sign in as the repository owner. Open your test repository → **Settings → Collaborators** (under **Access**) → **Add people**.
3. Search for the helper's GitHub username, select the correct account, and click **Add NAME to REPOSITORY**.
4. Sign in as the helper, open the invitation from GitHub's email, and accept it. Sending the invitation alone is not enough.
5. As the owner, check **Settings → Collaborators** again: the helper should have access, with no pending invitation.
6. Run:

```powershell
python main.py run yolo --tier base --execute
```

The helper merges the PR without a review. Existing branch rules still apply.

### Galaxy Brain

This workflow needs **two different accounts**. The helper posts questions, your primary account answers, and the helper marks those answers as accepted.

#### A. Save both tokens in `.env`

1. Keep the repository owner's classic token with **repo** selected in `GITHUB_TOKEN`.
2. Sign in to the **helper account** and create its own classic token with **repo** selected using the [token creation steps](#how-to-create-the-primary-token). If you already have a working helper classic **repo** token, reuse it.
3. Put that second token in `HELPER_TOKEN`. Check that `TARGET_REPO` points to your test repository, then save `.env`:

```dotenv
GITHUB_TOKEN=YOUR_REPOSITORY_OWNER_TOKEN
TARGET_REPO=technorant/test
HELPER_TOKEN=YOUR_SECOND_ACCOUNT_TOKEN
```

Replace the placeholders with your tokens locally. Other users should replace `technorant/test` with their own repository.

#### B. Invite the helper and accept the invitation

1. Sign in as the **repository owner** and open your test repository on GitHub.
2. Open **Settings → Collaborators**, under **Access**. GitHub may ask you to confirm your password.
3. Click **Add people**, search for the helper's GitHub username, and select the correct account.
4. Click **Add NAME to REPOSITORY** to send the invitation.
5. Sign in as the **helper account**, open the invitation from GitHub's email, and accept it. Make sure you accept while signed in to the helper, not the owner.
6. Switch back to the owner and check **Settings → Collaborators**. The helper must appear with access, not as a pending invitation. An accepted collaborator invitation gives the helper write access to a personal repository.

Already accepted an invitation for YOLO in this same repository? You can keep that access; no new invitation is needed. See [GitHub's invitation guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) if you get stuck.

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

Resolve any errors before continuing. Then choose either way to run:

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
