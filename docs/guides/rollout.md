# Rolling it out

A gate that blocks people on day one gets disabled on day two. The pieces are designed to be
turned on in order.

## 1. Observe

Merge the workflow and the policy with the `mergeproof` status **not** required. Every PR gets the
comment and the status; nothing is blocked. Watch for a week: which rules fire, which globs are
wrong, which requirement nobody understands. Fix the policy, not the contributors.

Rule severity says what the comment *reports*; a merge is blocked only once the status is
*required*. So the core rules can be `block` from the start and the report stays truthful.

## 2. Require

Add `mergeproof` to the required checks on the default branch. From now on the rules marked
`block` gate merges. Keep the heuristics, such as "the changelog changed", at `severity: warn`;
they nudge without stopping a hotfix.

## 3. Grow the policy from evidence

Add a rule when a class of regression slips through, and say in its `description` what it caught.
Remove or soften a rule that only ever produces noise.

## Replay before you tighten

"Will this rule annoy people" has a factual answer. `replay` rebuilds the context of pull requests
that already merged, evaluates a policy against each, and says what would have been blocked:

```sh
GITHUB_TOKEN=$(gh auth token) mergeproof replay --policy mergeproof.yaml --last 50 --repo OWNER/NAME
```

```
 #128  2026-09-14  pass     feat(search): paginate results
 #127  2026-09-13  fail     fix(tools): empty query no longer raises
       needs  fix-or-feature-has-live-evidence · before/after traces
 #126  2026-09-13  pass     docs: rollout guide
 ...
50 merged pull requests in OWNER/NAME; the policy applied to 31 and would have blocked 9
most common blockers:
    7  fix-or-feature-has-live-evidence · before/after traces
    2  tool-change-has-integration-tests · integration tests touched
```

`--against current` evaluates the policy on the default branch as well and marks the verdicts
that change, so a proposed tightening shows only what it adds. `--since 2026-08-01` bounds by
date, `-f json` is for scripts, and `--fail-on-block` makes it usable as a CI check on policy PRs.

Replay is read-only. It needs a token that can read the repository; nothing is posted. Checks
that call out, such as verified links, run for real, so an old trace that has since expired shows
as unverified, which is itself worth knowing.

`--save scenarios/` writes one file per pull request in the shape the examples use, so the cases
that mattered become fixtures the test suite runs forever.

## What to require in the first policy

Two rules carry most of the value in a codebase that agents change:

```yaml
- id: module-change-has-integration-tests
  when: { paths: ["src/tools/**/*.py"] }
  require:
    - check: tests.changed
      with:
        map: { "src/tools/{name}.py": "tests/integration/tools/test_{name}*.py" }
        existing_only: true          # only where the module already has a test file

- id: fix-or-feature-has-live-evidence
  when: { paths: ["src/**/*.py"], title: "^(fix|feat)(\\(.+\\))?!?: " }
  require:
    - check: evidence.links
      with: { key: traces, min_pairs: 1, verify: braintrust }
    - check: review.human_verified
```

Everything else can start as a warning.
