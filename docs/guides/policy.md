# Writing a policy

The policy is `mergeproof.yaml` at the repository root. It is read from the pull request's **base
branch**, so a pull request cannot change the rules that apply to it.

```yaml
version: 1
project: my-service          # optional label
evidence_block: evidence     # info string of the fenced block in the PR description

rules:
  - id: source-needs-tests           # unique, appears in every report
    description: Source changes ship with tests for the touched module.
    severity: block                  # block (default) or warn
    when:                            # all listed conditions must hold; lists are "any of"
      paths: ["src/**/*.py"]
      exclude_paths: ["src/**/__init__.py"]
    instructions: >                  # free text shown next to the requirements
      A regression test that fails before the change and passes after it.
    require:
      - check: tests.changed
        name: unit tests touched     # label in reports; defaults to the check id
        severity: block              # overrides the rule's severity for this requirement
        with:                        # parameters, validated against the check's schema
          map: { "src/{pkg}/{name}.py": "tests/**/test_{name}*.py" }
        instructions: ...            # overrides the rule's instructions for this requirement
```

`mergeproof validate` checks the file: unknown checks and bad parameters are reported with the
rule and requirement they belong to.

## `when`: which changes a rule applies to

| key | meaning |
|---|---|
| `paths` | at least one changed file matches one of these globs |
| `exclude_paths` | files matching these are ignored when evaluating `paths` |
| `labels` | the PR carries at least one of these labels |
| `title` | the PR title matches this regex (case-insensitive) |
| `base_branches` | the target branch matches one of these globs |
| `authors` | the PR author is one of these logins, e.g. `copilot[bot]` |

A rule without `when` applies to every pull request. Globs support `**`, `*`, `?` and `{name}`
captures; a capture in a `paths` glob is available to `tests.changed` templates.

## Severity and verdict

Each requirement ends in a status: `pass`, `fail`, `warn`, `pending` (evidence not there yet:
CI still running, reviewer has not verified), `skip` (not applicable), `error` (misconfigured or
crashed). The report's verdict is:

| verdict | when |
|---|---|
| `fail` | a `block` requirement failed or errored |
| `pending` | no failure, but a `block` requirement is pending |
| `warn` | only `warn`-severity requirements are unmet |
| `pass` | everything is satisfied |

`fail` and `pending` block the merge when the `mergeproof` status is required.

## The evidence block

Evidence lives in the PR description as a fenced YAML block whose info string is the policy's
`evidence_block` (default `evidence`). Several blocks merge; later keys win. Invalid YAML is reported
rather than ignored.

````markdown
```evidence
environment: staging
image: registry.example.com/app:pr-77-4444444
links:
  - what: search with an empty query
    before: https://logs.example.com/run/1
    after: https://logs.example.com/run/2
```
````

`mergeproof template` prints the block a change still needs, with placeholders.

## Checks

Every check and its parameters is listed in the [checks reference](../reference/checks.md).

## Verifiers

A verifier turns a link into yes or no. `http` ships in core. Others are plugins registered under
the `mergeproof.verifiers` entry-point group; see [Plugins](../extending/plugins.md) and the Langfuse example
in `examples/plugins/`.
