# Policy reference

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

### `tests.changed`

Changed source files come with changed test files.

| parameter | meaning |
|---|---|
| `map` | source glob with `{captures}` mapped to a test glob template, e.g. `src/{pkg}/{name}.py: tests/**/test_{name}*.py`. Every matching changed source file needs a changed file matching its expanded template |
| `any_of` | used when `map` is empty: pass if any changed file matches one of these globs |
| `ignore` | source globs exempt from `map` |

Each uncovered source file becomes a Check Run annotation on that file.

### `files.changed`

| parameter | meaning |
|---|---|
| `any_of` | at least one changed file matches |
| `all_of` | every glob matches at least one changed file |
| `none_of` | no changed file matches |

### `evidence.field`

A key in the evidence block is present and valid. `key` is a dotted path (`image.tag`).

| parameter | meaning |
|---|---|
| `equals` | exact value |
| `one_of` | list of accepted values |
| `matches` | regex a string value must match |
| `min_items` | minimum length of a list value |
| `example` | placeholder shown in the evidence template |
| `block` | evidence block tag, default `evidence` |

### `evidence.links`

Before/after link pairs under `key` (default `links`). Each item is a mapping with `before` and
`after` (and anything else, e.g. `what`).

| parameter | meaning |
|---|---|
| `min_pairs` | how many valid pairs are needed (default 1) |
| `pattern` | regex a link must match; named groups are passed to the verifier |
| `require_before` | require `before` as well as `after` (default true) |
| `distinct` | `before` and `after` must differ (default true) |
| `verify` | verifier name: `http` (link answers 2xx/3xx) or one from a plugin |
| `verify_options` | keyword options for the verifier, e.g. `{ auth_header_env: DASH_TOKEN }` |
| `example` | placeholder link in the evidence template |

### `ci.job_passed`

A check run on the head commit succeeded. Only the newest run per name counts, so a run cancelled
by a newer push is not a failure.

| parameter | meaning |
|---|---|
| `name` | check run name, or a regex when `regex: true` |
| `min_matches` | how many matching runs must succeed (default 1) |
| `missing` | `pending` (default) or `fail` when no run with that name exists yet |

### `review.human_verified`

A human other than the author posted the verification phrase.

| parameter | meaning |
|---|---|
| `phrase` | default `/verified` |
| `bind_to_head` | the comment must contain the 7-character head sha (default true); a new push invalidates it |
| `allowed_users` | logins allowed to verify; empty means any non-author human |
| `exclude_author` | default true |
| `require_review_state` | e.g. `APPROVED`: the phrase must come in a review with that state |

Bot accounts (`*[bot]`) never satisfy this check.

### `agent.verdict`

An automated reviewer posted a fenced `verdict` block:

````markdown
```verdict
check: trace-review
verdict: pass
head: 4444444
confidence: 0.85
summary: the after-trace returns the empty page; the before-trace raises.
```
````

| parameter | meaning |
|---|---|
| `name` | the `check:` value to look for |
| `authors` | logins allowed to post it, e.g. `github-actions[bot]` |
| `bind_to_head` | the block's `head` must match the current head (default true) |
| `min_confidence` | below this the requirement stays pending |

The newest matching verdict wins. Agents are witnesses; pair this with `review.human_verified`
for anything that matters.

### `pr.labels`, `pr.body`

`pr.labels`: `any_of`, `all_of`, `none_of`. `pr.body`: `sections` (Markdown headings that must
exist), `matches` (regex), `min_length`.

### `shell`

Runs `run` from the policy with `cwd`, `timeout`, `env`; exit 0 passes. The changed files are in
`MERGEPROOF_FILES`, the commit in `MERGEPROOF_HEAD_SHA`, the base branch in `MERGEPROOF_BASE_REF`.
Pull request content is never interpolated into the command. Not available when there is no
checkout.

## Verifiers

A verifier turns a link into yes or no. `http` ships in core. Others are plugins registered under
the `mergeproof.verifiers` entry-point group; see [plugins.md](plugins.md) and the Langfuse example
in `examples/plugins/`.
