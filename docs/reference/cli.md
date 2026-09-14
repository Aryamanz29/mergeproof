# Command line

```
mergeproof check          evaluate the policy and report; exit 0 pass, 1 fail, 2 pending
mergeproof explain        what this change must prove and what is missing
mergeproof template       the evidence block still missing for this change
mergeproof validate       check the policy file; with `extends`, list where each rule comes from
mergeproof init           write a starter policy
mergeproof checks         list available checks and their parameters
mergeproof agent-prompt   render an AGENTS.md section from the policy
mergeproof receipt        what a merged pull request proved, by merge sha or #number
mergeproof replay         evaluate a policy against merged pull requests; posts nothing
mergeproof context        print the pull request context as JSON      (plumbing)
mergeproof report         render a JSON report in another format      (plumbing)
mergeproof comment        post a JSON report to the pull request      (plumbing)
```

## Where the pull request comes from

| flag | source |
|---|---|
| `--local` (default) | `git diff` of the working tree against `--base` (default `origin/main`), uncommitted and untracked files included. `--body-file` and `--title` supply the PR text; `--gh` takes them from `gh pr view` |
| `--github` | the GitHub API; automatic inside Actions. Needs `GITHUB_TOKEN`; the PR is found from the event payload or `MERGEPROOF_REPO` + `MERGEPROOF_PR_NUMBER` |
| `--context FILE` | a JSON context produced earlier by `mergeproof context` (`-` for stdin) |

Checks that need the API (`ci.job_passed`, `review.human_verified`, `agent.verdict`) report
`pending` in local mode; `mergeproof checks` marks them.

## Output formats

`check` and `report` take `-f text` (default, for terminals), `md` (the PR comment), `json` (the
full report), `junit` (test-result renderers) and `rdjson` (reviewdog). `check -o FILE` writes the
JSON report as well as printing.

## Plumbing

Contexts and reports are plain JSON, so the stages compose:

<p align="center"><img src="../../assets/pipeline.svg" alt="context, check, report, comment as a pipeline" width="820"></p>

```sh
mergeproof context --github > pr.json                 # snapshot a PR
mergeproof check --context pr.json -f json > report.json
mergeproof report report.json -f md                   # render later, elsewhere
mergeproof comment report.json --status               # post it
```

Snapshots make policies testable: the examples ship scenario files that the integration suite runs
through the CLI and asserts the verdict each one claims.

## Exit codes

| code | meaning |
|---|---|
| 0 | pass, or only warnings |
| 1 | a blocking requirement failed or errored |
| 2 | a blocking requirement is pending |
| 3 | usage or policy error |

`report --exit-status` exits with the report's verdict code, for scripts.

## Environment

| variable | meaning |
|---|---|
| `MERGEPROOF_POLICY` | default policy path |
| `MERGEPROOF_BASE` | default base ref for local mode |
| `MERGEPROOF_REPO`, `MERGEPROOF_PR_NUMBER` | pull request for GitHub mode when there is no event payload |
| `GITHUB_TOKEN` / `GH_TOKEN` | GitHub API token |
| `GITHUB_API_URL` | for GitHub Enterprise |
