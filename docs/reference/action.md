# GitHub Action

```yaml
- uses: Aryamanz29/mergeproof@v0
  with:
    policy: mergeproof.yaml
```

## Inputs

| input | default | meaning |
|---|---|---|
| `policy` | `mergeproof.yaml` | path to the policy |
| `version` | `mergeproof` | pip requirement to install: a version spec, a path, a git URL |
| `plugins` | | extra pip requirements, for example verifier plugins, separated by spaces |
| `comment` | `true` | create or update the sticky comment |
| `review-comments` | `true` | post what is still needed as review comments on the files concerned, kept in sync |
| `status` | `true` | set the `mergeproof` commit status; the context to require |
| `pending-ok` | `false` | let the job succeed while evidence is pending; the status still says pending |
| `github-token` | `${{ github.token }}` | token used for every channel |

## Outputs

| output | meaning |
|---|---|
| `verdict` | `pass`, `warn`, `pending` or `fail` |
| `report` | path of the JSON report |
| `junit` | path of the JUnit rendering, for test-result reporters |
| `rdjson` | path of the reviewdog rendering |

All four files are uploaded as the `mergeproof-report` artifact.

## Permissions

| permission | needed for |
|---|---|
| `contents: read` | checkout |
| `pull-requests: write` | the comment and review comments |
| `statuses: write` | the commit status |
| `checks: read` | `ci.job_passed` reading other jobs' results |

## Events

Trigger on everything the gate reads:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
  issue_comment: { types: [created, edited] }
  check_suite:   { types: [completed] }
```

Comment and check-suite events do not carry the PR number where the action expects it; set
`MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}`.

## Exit codes

The job exits with the report's code: 0 pass or warn, 1 fail, 2 pending (0 with `pending-ok`),
3 usage or policy error.
