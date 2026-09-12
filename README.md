# mergeproof

**Proof before merge.** Pull requests earn their merge with evidence, not claims.

`mergeproof` is an evidence gate for pull requests. You declare, in one YAML file, what a change must
*prove* before it merges: tests for the touched modules, a green integration job, before/after
observability traces from a live environment, a human who actually opened those traces. CI enforces
it and posts one sticky report on the PR. The same file tells coding agents exactly what evidence to
produce, so the process stops living in review comments.

Built for agentic development: agents are good at claiming outcomes, so the gate checks artifacts,
verifies them against external systems when it can, and reserves the final attestation for a human
other than the author.

## Why not X?

| Tool | What it does well | Why it did not fit |
|---|---|---|
| [Danger JS](https://danger.systems/js/) | Rules in a `dangerfile`, sticky PR comment, plugins | Imperative JS per repo; no evidence schema; no agent-facing "what do I need to produce"; `danger-python` is unmaintained (2020) |
| [policy-bot](https://github.com/palantir/policy-bot) | Rich approval predicates (paths, teams, statuses, body regex) | Self-hosted GitHub App; approval only, cannot verify external artifacts like traces |
| [Evidence Gate](https://evidence-gate.dev/) | 25 fixed gate types, fail-closed | SaaS; evidence evaluated server-side; no custom gate types |
| MergeWarden / [agents-shipgate](https://github.com/ThreeMoonsLab/agents-shipgate) | Deterministic hygiene / tool-surface checks for AI PRs | Fixed check sets, not an extensible evidence framework |
| Checklist actions | Fail on unticked boxes | A checkbox is self-attestation, which is exactly what an agent will tick |

`mergeproof` borrows policy-bot's predicate vocabulary, Danger's sticky comment, and shipgate's
JSON report + exit codes, and adds the parts missing everywhere: a structured evidence block,
pluggable verifiers, head-sha-bound human attestation, and an `explain` command for agents.

## Install

```bash
pip install mergeproof            # or: uv tool install mergeproof
mergeproof init                   # writes a starter mergeproof.yaml
mergeproof checks                 # list built-in checks and their parameters
```

## A policy

```yaml
version: 1
project: mcp-server
rules:
  - id: tool-change-needs-unit-tests
    when: { paths: ["modelcontextprotocol/tools/**/*.py"] }
    require:
      - check: tests.changed
        with:
          map: { "modelcontextprotocol/tools/{name}.py": "modelcontextprotocol/tests/unit/**/test_{name}*.py" }
      - check: ci.job_passed
        with: { name: "Unit Tests", regex: true }

  - id: bugfix-live-evidence
    when: { title: "^(fix|feat)" , paths: ["modelcontextprotocol/**/*.py"] }
    instructions: Reproduce on the eval tenant, capture a trace, deploy the fix, repeat, capture again.
    require:
      - check: evidence.field
        with: { key: tenant, equals: staging }
      - check: evidence.traces
        with: { project: mcp-internal, min_pairs: 1, verify: true }
      - check: review.human_verified
        with: { phrase: "/verified", bind_to_head: true }
```

Evidence lives in the PR description as a fenced block agents can write and machines can read:

````markdown
```evidence
tenant: staging
image: registry/mcp-server:pr-582-b3ca7be
traces:
  - tool: query_assets
    before: https://www.braintrust.dev/app/org/p/mcp-internal/logs?r=b6f98332e178f658
    after:  https://www.braintrust.dev/app/org/p/mcp-internal/logs?r=db0100b2192984af
```
````

## Three commands, one policy

| Command | Who runs it | What it does |
|---|---|---|
| `mergeproof check --github --comment` | CI | Evaluates the policy, upserts one PR comment, sets the check red/green, writes `GITHUB_STEP_SUMMARY` and a JSON report |
| `mergeproof explain` | contributors and agents, locally | Diffs the working tree against `origin/main`, shows which rules apply, what is already satisfied, what is missing, and prints the evidence block to paste |
| `mergeproof agent-prompt` | you, once | Renders a Markdown section for `CLAUDE.md` / `AGENTS.md` generated from the policy, so agents read the exact rules CI enforces |

Statuses: `pass`, `fail`, `warn`, `pending` (evidence not there *yet*: CI running, reviewer has not
verified), `skip`, `error`. A rule's `severity` (`block` default, or `warn`) decides whether an unmet
requirement fails the check. `pending` fails the check by default; pass `--pending-ok` if you would
rather gate through branch protection on a separate status.

## Built-in checks

| id | proves |
|---|---|
| `tests.changed` | each changed source file (via `{capture}` globs) or any file has a changed test |
| `evidence.field` | a key in the evidence block exists / equals / matches / has N items |
| `evidence.traces` | before/after trace-link pairs from the right project; `verify: true` looks them up via Braintrust BTQL |
| `ci.job_passed` | a named check run on the head sha succeeded (pending while running) |
| `review.human_verified` | a non-author, non-bot comment `/verified <sha7>`; a new push invalidates it |
| `pr.labels` | any_of / all_of / none_of |
| `pr.body` | required sections, regex, min length |
| `shell` | an arbitrary command from the policy exits 0 (changed files in `$MERGEPROOF_FILES`) |
| `agent.verdict` | an allowed automated reviewer posted a head-bound ```verdict block with `verdict: pass` (see below) |

Rule matchers: `paths`, `exclude_paths`, `labels`, `title` (regex), `base_branches`, `authors`
(for example, apply stricter rules to `claude[bot]`).

## Non-deterministic checks (LLM reviewers)

Deterministic checks decide; agents testify. Any reviewer agent (GitHub Copilot custom agents,
`anthropics/claude-code-action`, an in-house reviewer) can participate by posting a comment with a
fenced `verdict` block, which `agent.verdict` turns into a normal requirement:

````markdown
```verdict
check: trace-review
verdict: pass
head: b3ca7be
confidence: 0.9
summary: after-trace shows auto_corrections populated; before-trace shows none.
```
````

```yaml
- check: agent.verdict
  with: { name: trace-review, authors: ["github-actions[bot]"], min_confidence: 0.8 }
```

Restrict `authors` to the bot that runs the agent, keep `bind_to_head` on so a new push invalidates
the verdict, and pair it with `review.human_verified` for anything that matters. If your agent
already expresses its result as labels (for example `reviewed` / `review-failed`), `pr.labels`
consumes those directly.

## Writing your own check

```python
from mergeproof import Check, CheckResult, Status
from pydantic import BaseModel


class ImageSmokeTested(Check):
    id = "image.smoke_tested"
    description = "The temporary image in the evidence block was exercised against the tenant."

    class Params(BaseModel):
        registry_prefix: str

    def run(self, ctx, params, files):
        tag = ctx.evidence().get("image")
        if not tag or not tag.startswith(params.registry_prefix):
            return CheckResult(
                status=Status.FAIL,
                summary="no image tag in evidence",
                fix="Build the branch image and record its tag under `image`.",
            )
        # ...query your registry / deployment API here...
        return CheckResult(status=Status.PASS, summary=f"{tag} smoke-tested")

    def explain(self, params):
        return f"An image under `{params.registry_prefix}` recorded under `image` and smoke-tested."

    def evidence_template(self, params):
        return {"image": f"{params.registry_prefix}<name>:pr-<n>-<sha7>"}
```

Register it in your package's `pyproject.toml`:

```toml
[project.entry-points."mergeproof.checks"]
"image.smoke_tested" = "mypkg.checks:ImageSmokeTested"
```

Install both packages in CI and the check id is usable in any policy.

## GitHub Actions

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
  issue_comment: { types: [created, edited] }   # re-run when a reviewer posts /verified
  check_suite:   { types: [completed] }         # re-run when CI jobs finish
jobs:
  mergeproof:
    if: github.event_name != 'issue_comment' || github.event.issue.pull_request
    runs-on: ubuntu-latest
    permissions: { contents: read, pull-requests: write, checks: read }
    steps:
      - uses: actions/checkout@v4
      - uses: Aryamanz29/mergeproof@v0.1.0
        with: { policy: mergeproof.yaml }
        env:
          BRAINTRUST_API_KEY: ${{ secrets.BRAINTRUST_API_KEY }}   # only for verify: true
          MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}
```

Mark the `mergeproof` check as required in branch protection / rulesets and the gate is enforced.

### Trust notes

- Read the policy from the base branch for PRs from forks; a PR can otherwise edit its own rules.
- `shell` runs commands from the policy only; PR content is exposed via environment variables, never interpolated.
- `review.human_verified` ignores `*[bot]` accounts and the PR author, and binds to the head sha.
- With `verify: true`, `evidence.traces` sends only trace ids and the project name to the Braintrust API.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
mergeproof explain --policy mergeproof.yaml   # the repo gates itself
```

MIT.
