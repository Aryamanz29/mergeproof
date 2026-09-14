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
Remove or soften a rule that only ever produces noise. `mergeproof explain` on old branches is a
cheap way to see what a new rule would have flagged.

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
