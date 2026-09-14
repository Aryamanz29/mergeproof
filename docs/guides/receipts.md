# Receipts

The gate is a live evaluation. Three months after a merge the comment may have been edited, the
trace links may have expired and the reviewer may have left. A receipt is the final report for the
merged commit, written down at merge time and kept in the repository, so "what proved this
change?" has an answer that needs no API and no third party.

## What is stored

When a pull request merges, the action evaluates it one last time and commits
`receipts/<merge commit sha>.json` to the `mergeproof-receipts` branch of the same repository. The
branch is created on first use. The file holds:

- the merge: pull request number, head sha, merge commit sha, who merged and when;
- the policy that applied: path and SHA-256 of its content, and the mergeproof version;
- the full report: every rule that matched, every requirement, its outcome, the evidence it found
  and the details it recorded (for example the trace ids a verifier confirmed).

The scorecard comment on the merged PR links to it.

## Reading one

```sh
mergeproof receipt 3f2c1ab                 # by merge commit sha
mergeproof receipt "#128"                  # by pull request number
mergeproof receipt 128 --json              # the whole document
```

Needs `GITHUB_TOKEN` and the repository, taken from `GITHUB_REPOSITORY` or `--repo`. The summary
lists who merged what and one line per requirement:

```
#128 merged as 3f2c1ab by lead at 2026-09-14T18:02:25Z
head 40395ea · policy mergeproof.yaml (9c1d3a2e0b7f) · mergeproof 0.8.0
verdict: pass · All 5 requirements satisfied

[   pass] ci-green · lint: 1 run succeeded
[   pass] source-needs-tests · unit tests touched: tests changed for all 2 mapped source files
```

## Turning it on

The action writes receipts by default (`receipt: "true"`). Two things must be true for it to work:

1. the workflow subscribes to `pull_request: closed`, so the action runs when the PR merges;
2. the job has `contents: write`, so it can commit to the receipt branch.

Without them nothing breaks: the action logs that it could not write the receipt and posts the
comment as usual. The [example workflow](https://github.com/Aryamanz29/mergeproof/blob/main/examples/github-workflow.yml)
has both. If the gate job depends on a whole CI matrix, a separate small workflow on `closed` is
cheaper; this repository's own [`receipt.yml`](https://github.com/Aryamanz29/mergeproof/blob/main/.github/workflows/receipt.yml)
is that.

Rulesets target the default branch, so the receipt branch is not protected by them; protect it
separately if the history must be tamper-evident (a ruleset allowing only the Actions token to
push, no force pushes, no deletion).

## Why a branch

A workflow artifact expires. A release asset only exists at release time. A comment can be edited.
A branch in the same repository is durable, versioned, readable with `git`, and travels with forks
and mirrors. Each receipt is one commit, so `git log mergeproof-receipts` is the audit trail.
