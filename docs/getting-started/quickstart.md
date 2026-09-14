# Quickstart

Three steps: a policy, a workflow, a required check.

## 1. Write the policy

`mergeproof init` writes a starter `mergeproof.yaml` at the repository root. A policy is a list of
rules; each says *when* it applies and what it *requires*.

```yaml
version: 1
rules:
  - id: source-needs-tests
    description: Source changes ship with tests for the touched module.
    when:
      paths: ["src/**/*.py"]
    require:
      - check: tests.changed
        with: { map: { "src/{pkg}/{name}.py": "tests/**/test_{name}*.py" } }
      - check: ci.job_passed
        with: { name: "^unit", regex: true }

  - id: fix-needs-live-evidence
    description: Bug fixes show the behaviour before and after on staging.
    when:
      title: "^fix"
    require:
      - check: evidence.field
        with: { key: environment, equals: staging }
      - check: evidence.links
        with: { min_pairs: 1 }
      - check: review.human_verified
```

`mergeproof validate` checks it; `mergeproof explain` shows what the current diff would have to
prove. See [Writing a policy](../guides/policy.md).

## 2. Add the workflow

```yaml title=".github/workflows/mergeproof.yml"
name: mergeproof
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
  issue_comment: { types: [created, edited] }   # /verified lands here
  check_suite:   { types: [completed] }         # re-check when CI finishes
jobs:
  gate:
    if: github.event_name != 'issue_comment' || github.event.issue.pull_request
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write, statuses: write, checks: read }
    steps:
      - uses: actions/checkout@v4
        with: { ref: ${{ github.event.repository.default_branch }} }   # policy from the base branch
      - uses: Aryamanz29/mergeproof@v0
        env:
          MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}
```

The full file, with comments, is [`examples/github-workflow.yml`](https://github.com/Aryamanz29/mergeproof/blob/main/examples/github-workflow.yml).

## 3. Require the status

GitHub merges anything unless a ruleset says otherwise. Require **one** context, `mergeproof`, on
your default branch; the policy decides what stands behind it. Details and the exact API call are
in [GitHub setup](../guides/github.md#making-it-block-the-ruleset).

## What happens next

Every pull request gets a scorecard comment, a `mergeproof` commit status, and review comments on
the files that still need something. Contributors run `mergeproof explain` locally to see the same
list before pushing. See [What a pull request sees](what-you-see.md).
