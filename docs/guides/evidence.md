# Evidence

Evidence is anything a check can inspect: a changed file, a green job, a link that resolves, a
comment from a person. Most of it is found in the pull request itself. The rest, the part a
contributor has to supply, lives in the PR description as a fenced YAML block.

## The evidence block

````markdown
```evidence
environment: staging
preview: https://pr-77.preview.example.com
traces:
  - what: search with an empty query
    before: https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r=b6f98332e178f658
    after:  https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r=db0100b2192984af
screens:
  - what: cart
    url: https://shots.example.com/pr77-cart.png
  - what: checkout
    url: https://shots.example.com/pr77-checkout.png
```
````

The info string is the policy's `evidence_block` (default `evidence`). Several blocks merge, later
keys win, and invalid YAML is reported rather than ignored. Agents can write this; people can skim
it.

`mergeproof template` prints exactly the block a change still needs, with placeholders. The same
block appears in the PR comment while it is missing.

## Values and artifacts

Two checks read the block. `evidence.field` looks at a value: it exists, equals something, matches
a regex, is one of a list. `evidence.artifacts` looks at links, and asks what *kind* of artifact
they are:

| kind | what it says | example |
|---|---|---|
| `pair` | the behaviour before the change and after it | two traces, two screenshots of the same screen |
| `single` | one thing to open | a preview deployment, a dashboard, a report |
| `set` | one link per item in a list | every screen a UI change touched, one log per environment |

```yaml
- check: evidence.artifacts
  name: before/after traces
  with: { key: traces, kind: pair, min_items: 1, verify: braintrust }

- check: evidence.artifacts
  name: preview deployment
  with: { key: preview, kind: single, pattern: "^https://" }

- check: evidence.artifacts
  name: a screenshot per screen
  with: { key: screens, kind: set, min_items: 2, pattern: "\\.png$" }
```

The kind decides the shape the block must have and what the template prints. `evidence.links`
is the `pair` kind under its own name, with `min_pairs` instead of `min_items`; it is what older
policies and the Langfuse and Braintrust plugins use, and it is not going anywhere.

## Verified links

A pasted link should have to be real. Any kind takes a `pattern` with named groups and a
`verify`:

```yaml
- check: evidence.artifacts
  with:
    key: traces
    kind: pair
    pattern: "^(?P<host>https?://[^/]+)/project/(?P<project>[^/]+)/traces/(?P<trace_id>[\\w-]+)"
    verify: langfuse
```

`http` ships in core (the URL answers 2xx). Anything vendor-specific is a verifier plugin; Langfuse
and Braintrust ones live in `examples/plugins/` and are a few dozen lines each. See
[Plugins](../extending/plugins.md).

A verified link is more than a tick. The verifier reports what it found and the comment shows it
next to the link, so a reviewer can tell a real trace from an empty one before opening it:

```
before: braintrust · mcp-internal · search · 3 spans · 2026-09-14T17:02:01Z
after:  braintrust · mcp-internal · search · 14 spans · 2026-09-14T17:41:12Z
```

The same lines go into the [receipt](receipts.md) when the pull request merges.

## Human verification

Some evidence cannot be produced by the author, and none of it by a bot. `review.human_verified`
looks for a phrase, `/verified` by default, from a person other than the author, bound to the
7-character head sha:

```
/verified 44501f5
```

A new push changes the sha and invalidates the verification. `allowed_users` narrows who may
verify; `require_review_state: APPROVED` demands it inside an approving review, and
`accept_approval: true` lets an approving review of the head commit count on its own.

## Automated reviewers as witnesses

LLM review agents can take part without becoming the gate. They post a `verdict` block:

````markdown
```verdict
check: trace-review
verdict: pass
head: 44501f5
confidence: 0.85
summary: the after-trace returns the empty page; the before-trace raises.
```
````

`agent.verdict` accepts it only from allowed bot accounts and only for the current head. Pair it
with `review.human_verified` for anything that matters.

## What evidence is not

- A ticked checkbox. Checklists are self-attestation.
- A claim in the description. "Tested on staging" is text; a trace link is evidence.
- A green job on a stale commit. Only runs on the head commit count, and only the newest per name.
