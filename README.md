<p align="center">
  <img src="https://raw.githubusercontent.com/Aryamanz29/mergeproof/main/docs/assets/logo-wordmark.svg" alt="mergeproof: proof before merge" width="420">
</p>

<p align="center"><strong>Proof before merge.</strong> Pull requests earn their merge with evidence, not claims.</p>

<p align="center">
  <a href="https://github.com/Aryamanz29/mergeproof/actions/workflows/ci.yml"><img src="https://github.com/Aryamanz29/mergeproof/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/mergeproof/"><img src="https://img.shields.io/pypi/v/mergeproof?color=7c3aed" alt="PyPI"></a>
  <a href="https://pypi.org/project/mergeproof/"><img src="https://img.shields.io/pypi/pyversions/mergeproof" alt="Python versions"></a>
  <a href="https://github.com/marketplace/actions/mergeproof"><img src="https://img.shields.io/badge/Marketplace-mergeproof-7c3aed?logo=github" alt="GitHub Marketplace"></a>
  <a href="https://github.com/Aryamanz29/mergeproof/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

<p align="center">
  <a href="https://aryamanz29.github.io/mergeproof/">Documentation</a> ·
  <a href="https://aryamanz29.github.io/mergeproof/getting-started/quickstart/">Quickstart</a> ·
  <a href="https://aryamanz29.github.io/mergeproof/reference/checks/">Checks</a> ·
  <a href="https://github.com/Aryamanz29/mergeproof/tree/main/examples/">Examples</a> ·
  <a href="https://github.com/Aryamanz29/mergeproof/blob/main/CHANGELOG.md">Changelog</a>
</p>

---

A pull request says *"added tests, verified on staging"*. That costs nothing to type. `mergeproof`
turns it into something CI can check: one YAML file in the repository says what a change must
**prove** before it merges, the action checks the proof on every push, and the same file tells
coding agents what to produce before they open the PR.

<p align="center"><img src="https://raw.githubusercontent.com/Aryamanz29/mergeproof/main/docs/assets/pr-comment.png" alt="The mergeproof comment on a pull request: one pill per rule, the one requirement still missing with what to do, and the satisfied ones underneath" width="820"></p>

<p align="center"><sub>A real comment. One pill per rule, then only what blocks the merge and what to do about it; the rest is the receipt.</sub></p>

## How it works

<p align="center"><img src="https://raw.githubusercontent.com/Aryamanz29/mergeproof/main/docs/assets/how-it-works.svg" alt="One policy file. Contributors and agents read it before pushing; the action enforces it against the diff, CI runs, evidence block and reviews; the pull request gets a scorecard comment, the mergeproof commit status and review comments on the files." width="900"></p>

- **One policy file.** A rule pairs a `when` (paths, labels, title, base branch) with what it
  `require`s: checks with parameters. Nothing to script.
- **Evidence, not attestation.** Tests must be in the diff. Jobs must be green on the head commit.
  Links must resolve at their source. Sign-off is a human approval bound to the commit; a new push
  invalidates it.
- **One required status.** Rulesets require `mergeproof`; the policy decides what stands behind it,
  CI jobs included. When no rule applies, nothing is posted and nothing blocks.
- **Agents read the same file.** They learn what to prove and check their own work before opening
  the PR. They cannot approve anything.

## Quickstart

**1. Write the policy.** `mergeproof init` writes a starter; this is the shape:

```yaml
# mergeproof.yaml
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
      - check: evidence.links
        with: { key: traces, min_pairs: 1, verify: http }
      - check: review.human_verified
        with: { accept_approval: true }
```

**2. Add the workflow.** Full version with comments: [`examples/github-workflow.yml`](https://github.com/Aryamanz29/mergeproof/blob/main/examples/github-workflow.yml).

```yaml
# .github/workflows/mergeproof.yml
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
  issue_comment: { types: [created, edited] }
  check_suite:   { types: [completed] }
jobs:
  gate:
    if: github.event_name != 'issue_comment' || github.event.issue.pull_request
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write, statuses: write, checks: read }
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.repository.default_branch }}   # policy from the base branch
      - uses: Aryamanz29/mergeproof@v1
        env:
          MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}
```

**3. Require the `mergeproof` status** on your default branch. Until you do, the gate only
reports, which is the right way to [roll it out](https://aryamanz29.github.io/mergeproof/guides/rollout/).

## Before you push

`mergeproof explain` runs the policy against the working tree and prints what is still missing,
in the same words the PR comment will use. Agents run it in their loop; people run it before
opening the PR.

<p align="center"><img src="https://raw.githubusercontent.com/Aryamanz29/mergeproof/main/docs/assets/explain.png" alt="mergeproof explain in a terminal: the rule that applies, the requirement that is missing, and the fix" width="820"></p>

```sh
pip install mergeproof            # or: uv tool install mergeproof, uvx mergeproof
mergeproof explain                # what this diff must prove
mergeproof template               # the evidence block still missing, ready to paste
mergeproof agent-prompt >> AGENTS.md
```

## What it can check

| check | proves |
|---|---|
| `tests.changed` | changed source files come with changed tests, mapped by `{capture}` globs; `existing_only` skips modules that have no test file yet |
| `ci.job_passed` | a named check run succeeded on the head commit (newest run per name; superseded runs are ignored) |
| `evidence.artifacts` | links in the evidence block by kind: before/after `pair`, one `single`, or a `set`; verified at their source by a pluggable verifier |
| `evidence.links` | the `pair` kind under its own name: before/after link pairs |
| `evidence.field` | a key in the evidence block exists and has an acceptable value |
| `review.human_verified` | a reviewer other than the author approved the head commit, or posted `/verified <sha>` |
| `agent.verdict` | an allowed automated reviewer posted a head-bound verdict block |
| `files.changed` | the change touches, or avoids, certain paths |
| `pr.labels`, `pr.body` | labels present or absent; description sections, regex, length |
| `shell` | a command from the policy exits 0 |

Parameters for each: `mergeproof checks`, or the
[checks reference](https://aryamanz29.github.io/mergeproof/reference/checks/). Anything
vendor-specific is a plugin: the [Langfuse](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-langfuse) and
[Braintrust](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-braintrust) verifiers are a dozen lines each.

## Evidence

What the contributor supplies goes in the PR description as a fenced block that agents can write
and machines can read. `mergeproof template` prints the one a change still needs.

````markdown
```evidence
environment: staging
traces:
  - what: search with an empty query
    before: https://www.braintrust.dev/app/acme/p/service/logs?r=b6f98332e178f658
    after:  https://www.braintrust.dev/app/acme/p/service/logs?r=db0100b2192984af
```
````

Everything else is found in the pull request itself: the diff, the check runs, the reviews.

## Where it reports

| channel | what |
|---|---|
| comment | the scorecard above, one per PR, updated in place |
| commit status `mergeproof` | `4 of 5 requirements satisfied, 1 missing` in the merge box; the context to require |
| review comments | each open requirement on the file it concerns, updated as the PR changes, removed once satisfied |
| job annotations | the same findings on the workflow run and in the diff |
| JUnit and reviewdog files | for renderers you already use |
| receipt | on merge, the final report is committed to a `mergeproof-receipts` branch; `mergeproof receipt <sha>` answers "what proved this change?" months later |

## Run without installing

```sh
uvx mergeproof explain
docker run --rm -v "$PWD":/repo ghcr.io/aryamanz29/mergeproof check --local
```

Images are tagged `X.Y.Z`, `X.Y`, `X` and `latest` per release, `edge` for `main`.

## Documentation

**[aryamanz29.github.io/mergeproof](https://aryamanz29.github.io/mergeproof/)**

| | |
|---|---|
| [Getting started](https://aryamanz29.github.io/mergeproof/getting-started/install/) | install, the three-step setup, what a pull request sees |
| [Guides](https://aryamanz29.github.io/mergeproof/guides/policy/) | writing a policy, evidence, GitHub setup, coding agents, rolling out without blocking anyone, the examples |
| [Reference](https://aryamanz29.github.io/mergeproof/reference/checks/) | every check and parameter, the command line, the action's inputs and outputs |
| [Extending](https://aryamanz29.github.io/mergeproof/extending/plugins/) | checks and verifiers as plugins |
| [Project](https://aryamanz29.github.io/mergeproof/project/contributing/) | contributing, releasing, FAQ |

## How it compares

[Danger](https://danger.systems/js/) runs rules written in JavaScript and comments on the PR.
[policy-bot](https://github.com/palantir/policy-bot) enforces approval policies from GitHub-native
data. Checklist actions fail on unticked boxes. Hosted evidence gates evaluate your artifacts on
their servers. `mergeproof` is declarative, has a notion of evidence that can be verified at its
source, explains itself to agents, and runs entirely in your CI.

## Contributing

`make setup`, then `make lint typecheck test`. Pull requests here are gated by this repository's own
`mergeproof.yaml`. See [CONTRIBUTING.md](https://github.com/Aryamanz29/mergeproof/blob/main/CONTRIBUTING.md). MIT licensed.
