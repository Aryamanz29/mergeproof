# Checks

Every built-in check, what it proves, and the parameters it takes under `with:`. `mergeproof checks` prints the same list with defaults. Plugins add more; see [Plugins](../extending/plugins.md).

## `tests.changed`

Changed source files come with changed test files.

| parameter | meaning |
|---|---|
| `map` | source glob with `{captures}` mapped to a test glob template, e.g. `src/{pkg}/{name}.py: tests/**/test_{name}*.py`. Every matching changed source file needs a changed file matching its expanded template |
| `any_of` | used when `map` is empty: pass if any changed file matches one of these globs |
| `ignore` | source globs exempt from `map` |
| `existing_only` | only require a test change when a file matching the expanded test glob already exists in the repository; a source whose test module does not exist yet is skipped and listed. Use it for "integration tests in the module, if the module has them" |

Each uncovered source file becomes a Check Run annotation on that file.

## `files.changed`

| parameter | meaning |
|---|---|
| `any_of` | at least one changed file matches |
| `all_of` | every glob matches at least one changed file |
| `none_of` | no changed file matches |

## `evidence.field`

A key in the evidence block is present and valid. `key` is a dotted path (`image.tag`).

| parameter | meaning |
|---|---|
| `equals` | exact value |
| `one_of` | list of accepted values |
| `matches` | regex a string value must match |
| `min_items` | minimum length of a list value |
| `example` | placeholder shown in the evidence template |
| `block` | evidence block tag, default `evidence` |

## `evidence.links`

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

## `ci.job_passed`

A check run on the head commit succeeded. Only the newest run per name counts, so a run cancelled
by a newer push is not a failure.

| parameter | meaning |
|---|---|
| `name` | check run name, or a regex when `regex: true` |
| `min_matches` | how many matching runs must succeed (default 1) |
| `missing` | `pending` (default) or `fail` when no run with that name exists yet |

## `review.human_verified`

A human other than the author verified the evidence: the verification phrase in a comment, or an
approving review when `accept_approval` is on.

| parameter | meaning |
|---|---|
| `phrase` | default `/verified` |
| `accept_approval` | an approving review counts, without the phrase; with `bind_to_head` the review must be on the head commit, so a new push asks for a fresh approval (default false) |
| `bind_to_head` | the comment must contain the 7-character head sha (default true); a new push invalidates it |
| `allowed_users` | logins allowed to verify; empty means any non-author human |
| `exclude_author` | default true |
| `require_review_state` | e.g. `APPROVED`: the phrase must come in a review with that state |

Bot accounts (`*[bot]`) never satisfy this check.

## `agent.verdict`

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

## `pr.labels`, `pr.body`

`pr.labels`: `any_of`, `all_of`, `none_of`. `pr.body`: `sections` (Markdown headings that must
exist), `matches` (regex), `min_length`.

## `shell`

Runs `run` from the policy with `cwd`, `timeout`, `env`; exit 0 passes. The changed files are in
`MERGEPROOF_FILES`, the commit in `MERGEPROOF_HEAD_SHA`, the base branch in `MERGEPROOF_BASE_REF`.
Pull request content is never interpolated into the command. Not available when there is no
checkout.
