# GitHub setup

## The workflow

Copy [`examples/github-workflow.yml`](https://github.com/Aryamanz29/mergeproof/blob/main/examples/github-workflow.yml) to
`.github/workflows/mergeproof.yml`. The important parts:

- **Events.** `pull_request` for pushes, edits and labels; `issue_comment` because `/verified` and
  agent verdicts arrive as comments; `check_suite: completed` so the gate re-evaluates when CI
  finishes. The `if:` filters out comments on plain issues.
- **Policy from the base branch.** The checkout uses the default branch, so a pull request cannot
  edit its own rules.
- **Permissions.** `pull-requests: write` for the comment and review comments, `statuses: write`
  for the commit status, `checks: read` so `ci.job_passed` can see other jobs.
- **`MERGEPROOF_PR_NUMBER`.** Comment and check-suite events do not carry the PR number where the
  action expects it; this line supplies it.

### Action inputs and outputs

| input | default | meaning |
|---|---|---|
| `policy` | `mergeproof.yaml` | path to the policy |
| `version` | `mergeproof` | pip requirement to install: a version spec, a path, a git URL |
| `plugins` | | extra pip requirements, e.g. verifier plugins |
| `comment` | `true` | create or update the sticky comment |
| `review-comments` | `true` | post what is still needed as file-level review comments, kept in sync on every run |
| `status` | `true` | set the `mergeproof` commit status; this is the row to require |
| `pending-ok` | `false` | let the job succeed while evidence is pending; the status still says pending |
| `github-token` | `${{ github.token }}` | token used for all three channels |

Outputs: `verdict` (`pass`, `warn`, `pending`, `fail`), and the paths `report` (JSON), `junit`,
`rdjson`. All four files are uploaded as the `mergeproof-report` artifact.

Pin `@v0` to follow releases, or `@v0.2.0` for an exact one.

## Making it block: the ruleset

GitHub merges anything unless a ruleset requires specific checks. Require **one** context,
`mergeproof` (the commit status); the policy decides what stands behind it, CI jobs included (see the `ci-green` rule
in this repository's own `mergeproof.yaml`). Rulesets need a public repository or a paid plan.

```sh
gh api -X POST repos/OWNER/REPO/rulesets --input ruleset.json
```

```json
{ "name": "main: pull requests with evidence", "target": "branch", "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "pull_request", "parameters": { "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true, "require_code_owner_review": false,
        "require_last_push_approval": false, "required_review_thread_resolution": false } },
    { "type": "required_status_checks", "parameters": { "strict_required_status_checks_policy": false,
        "required_status_checks": [ { "context": "mergeproof" } ] } } ] }
```

Why `pending-ok: "true"` is the usual choice: the workflow job then says "the tool ran", while
the required `mergeproof` status stays `pending` until evidence arrives, and a pending required
status blocks the merge button. Green job, blocked merge, clear reason.

## The report channels

| channel | where it shows | what it carries |
|---|---|---|
| comment | the PR conversation, one comment updated in place | the scorecard: one pill per rule, one sentence, the requirements that block with what to do, the evidence template, and everything else as a receipt |
| commit status | the merge box, requireable | `3 of 5 requirements satisfied, 2 pending`, linking to the comment. Statuses have no check-suite affinity, so a re-run on the same commit, a reopen, or a bot-authored PR all update it correctly |
| review comments | the Files changed tab, on the file concerned | one comment per unmet requirement: a missing test on the source file, a PR-level requirement on the first file that made its rule apply. Created, updated and removed as the PR evolves |
| job annotations | the workflow job's row and the diff | "expected a changed test matching …" on the source file, emitted as workflow commands, so they are always on the newest run |
| receipt | `receipts/<merge sha>.json` on the `mergeproof-receipts` branch | the final report for the merged commit, written when the PR merges; see [Receipts](receipts.md) |

No comment is posted when no rule applies to a change; an existing comment is still updated.

## Rendering with tools you already use

The action also writes **JUnit XML** (one suite per rule, one case per requirement) and
**reviewdog RDJSON** (one diagnostic per file annotation), so existing renderers can present the
gate:

```yaml
      - uses: Aryamanz29/mergeproof@v0
        id: gate
      - uses: EnricoMi/publish-unit-test-result-action@v2     # rich check run with counts and history
        if: always()
        with: { files: mergeproof-junit.xml, check_name: mergeproof requirements, comment_mode: off }
      - uses: reviewdog/action-setup@v1                       # inline review comments on the files
      - run: reviewdog -f=rdjson -reporter=github-pr-review -level=error < mergeproof.rdjson
        env: { REVIEWDOG_GITHUB_API_TOKEN: ${{ github.token }} }
```

`dorny/test-reporter` reads the same JUnit file. Locally: `mergeproof check -f junit` / `-f rdjson`.

## Posting as your own App

The avatar and author on the comment and the status belong to the token that created them.
With the default token that is `github-actions`. To post as **mergeproof** with your logo:

1. Create a GitHub App: name `mergeproof`, logo `docs/assets/logo.svg`, webhook inactive. Repository
   permissions: Checks read and write, Commit statuses read and write, Pull requests read and write,
   Contents read, Metadata read. "Any account" if other repositories of yours should install it.
2. Install it on the repository. Note the App ID and generate a private key.
3. Give the workflow the credentials:

   ```sh
   gh variable set MERGEPROOF_APP_ID --body <app id> --repo OWNER/REPO
   gh secret set MERGEPROOF_APP_KEY --repo OWNER/REPO < mergeproof.private-key.pem
   ```

4. Mint the token and pass it to the action:

   ```yaml
         - uses: actions/create-github-app-token@v1
           id: app
           with:
             app-id: ${{ vars.MERGEPROOF_APP_ID }}
             private-key: ${{ secrets.MERGEPROOF_APP_KEY }}
         - uses: Aryamanz29/mergeproof@v0
           with:
             github-token: ${{ steps.app.outputs.token }}
   ```

The private key lets its holder act as the App everywhere it is installed, so share it only within
one account or organisation. Another organisation should create its own App; the action and the
policy are identical. The workflow job row itself keeps the Actions icon; naming the job
`🛡️ mergeproof` puts the mark there as text.

## Checking the setup

`mergeproof doctor` reads what this page describes and reports what is off, with the fix:

```
[   ok] policy: mergeproof.yaml: 4 rule(s), every check known
[error] workflow: .github/workflows/mergeproof.yml: the policy reads comments (review.human_verified) but the workflow does not run on issue_comment
        fix: add `issue_comment: { types: [created, edited] }` under `on:`; verification would otherwise wait for the next push
[ warn] workflow: .github/workflows/mergeproof.yml: `contents: write` is missing; needed for writing receipts; without it the action logs and skips them
        fix: add `contents: write` to the job's `permissions:`
[error] repository: acme/svc: the `mergeproof` status is not required on main (ruleset requires nothing)
        fix: add the `mergeproof` context to the required status checks; until then the gate only reports

2 error(s), 1 warning(s)
```

It checks: the policy validates and every verifier it names is installed; a workflow uses the
action with a pinned ref; `pull_request` covers pushes, edits, labels and `closed` for receipts;
`issue_comment` and `check_suite` are subscribed when the policy needs them, with
`MERGEPROOF_PR_NUMBER` set; permissions cover the enabled channels; the checkout reads the policy
from the base branch; and, with a token, that the `mergeproof` status is required on the default
branch. It reports only what it looked at; the repository part is skipped without a token.

## Security notes

- The policy is read from the base branch; PRs from forks cannot change it.
- `shell` commands come from the policy, never from PR content; PR data reaches them only through
  environment variables.
- `review.human_verified` ignores bot accounts and the author, and binds to the head sha.
- Verifiers send only the link (or ids parsed from it) to the backend they check.
