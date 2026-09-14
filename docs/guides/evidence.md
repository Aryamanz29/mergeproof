# Evidence

Evidence is anything a check can inspect: a changed file, a green job, a link that resolves, a
comment from a person. Most of it is found in the pull request itself. The rest, the part a
contributor has to supply, lives in the PR description as a fenced YAML block.

## The evidence block

````markdown
```evidence
environment: staging
image: registry.example.com/app:pr-77-4444444
traces:
  - what: search with an empty query
    before: https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r=b6f98332e178f658
    after:  https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r=db0100b2192984af
```
````

The info string is the policy's `evidence_block` (default `evidence`). Several blocks merge, later
keys win, and invalid YAML is reported rather than ignored. Agents can write this; people can skim
it.

`mergeproof template` prints exactly the block a change still needs, with placeholders. The same
block appears in the PR comment while it is missing.

## Verified links

A pasted link should have to be real. `evidence.links` accepts before/after pairs, a regex with
named groups, and a verifier:

```yaml
- check: evidence.links
  with:
    key: traces
    pattern: "^(?P<host>https?://[^/]+)/project/(?P<project>[^/]+)/traces/(?P<trace_id>[\\w-]+)"
    verify: langfuse
```

`http` ships in core (the URL answers 2xx). Anything vendor-specific is a verifier plugin; Langfuse
and Braintrust ones live in `examples/plugins/` and are a dozen lines each. See
[Plugins](../extending/plugins.md).

## Human verification

Some evidence cannot be produced by the author, and none of it by a bot. `review.human_verified`
looks for a phrase, `/verified` by default, from a person other than the author, bound to the
7-character head sha:

```
/verified 44501f5
```

A new push changes the sha and invalidates the verification. `allowed_users` narrows who may
verify; `require_review_state: APPROVED` demands it inside an approving review.

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
