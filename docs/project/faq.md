# FAQ and troubleshooting

## The merge box says "Expected — waiting for status to be reported"

The required context is not being produced. Check that the workflow ran on this PR (bot-authored
PRs opened with the workflow token do not trigger CI until reopened) and that `status: "true"` is
in effect. If you require a *check run* instead of the status, GitHub matches it against the newest
check suite only; use the status.

## The gate says "policy not found" on the very first PR

The workflow reads the policy from the default branch, on purpose, so a PR cannot change its own
rules. The PR that introduces the policy is the one PR where that file is not yet on `main`. Every
later PR finds it.

## The gate posts nothing on a PR

No rule applied to that change. That is by design: docs-only or CI-only changes should not meet
the gate. `mergeproof explain` on the branch shows which rules would match.

## A requirement is pending forever

Pending means the evidence is not there *yet*: a CI job still running, a reviewer who has not
posted `/verified <sha>`. The comment is re-evaluated on push, label, comment and CI completion;
make sure the workflow subscribes to `issue_comment` and `check_suite`.

## The plugin does not install in CI

Pass it through the action's `plugins` input as a pip requirement. From a git repository
subdirectory: `git+https://github.com/OWNER/REPO@REF#subdirectory=path/to/plugin`.

## Rulesets are not available

Rulesets need a public repository or a paid plan. Classic branch protection can require the same
`mergeproof` context.

## Why is the job row still showing the GitHub Actions avatar?

Because the workflow token belongs to GitHub Actions. Posting under your own name and logo needs a
GitHub App token; see [GitHub setup](../guides/github.md#posting-as-your-own-app).
