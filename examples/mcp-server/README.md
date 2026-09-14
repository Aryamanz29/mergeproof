# mcp-server

A policy for a repository that ships an MCP server. Tool behaviour is what agents rely on, so a
fix has to show itself on a live deployment, not just in a unit test.

## Tracing with open-source tools

The policy expects before/after trace links. Braintrust, Langfuse, Arize Phoenix and Jaeger all
give every trace a stable URL; the difference is only how you prove a link is real:

| backend | licence | link shape | lookup API |
|---|---|---|---|
| [Langfuse](https://langfuse.com) | MIT, self-host | `https://<host>/project/<id>/traces/<trace-id>` | `GET /api/public/traces/{id}` (basic auth) |
| [Arize Phoenix](https://github.com/Arize-ai/phoenix) | ELv2, self-host | `https://<host>/projects/<id>/traces/<trace-id>` | GraphQL / REST |
| [Jaeger](https://www.jaegertracing.io) | Apache-2.0 | `https://<host>/trace/<trace-id>` | `GET /api/traces/{id}` |

Langfuse also ingests OpenTelemetry, so an MCP server instrumented with the OTel SDK needs no
vendor code. This example uses it through the [`mergeproof-langfuse`](../plugins/mergeproof-langfuse/)
plugin (`verify: langfuse`). Writing a verifier for the other two is a dozen lines; see the plugin.

## Workflow the policy encodes

1. Change a tool, add a failing unit test, make it pass.
2. Build the branch image, deploy it to staging, reproduce the bug with the agent client, keep the trace URL.
3. Deploy the fixed image, repeat the exact call, keep that trace URL.
4. Put both in the PR's evidence block. `mergeproof template` prints the skeleton.
5. The review agent posts its `verdict` block; a human opens the traces and comments `/verified <sha7>`.

## Scenarios

| file | expected |
|---|---|
| `fix-without-evidence.json` | fail: tool changed with tests, but no evidence block |
| `fix-awaiting-review.json` | pending: evidence present and verified, no human sign-off yet |
| `fix-verified.json` | pass |
| `fix-approved.json` | pass: the reviewer approved the head commit instead of posting the phrase |
| `fix-approved-before-last-push.json` | pending: the approval is on an older commit |
| `prompt-change-above-the-bar.json` | pass: a prompt change with a golden-dataset run scoring 0.85 on `correctness` |
| `prompt-change-below-the-bar.json` | fail: the same change with a run scoring 0.55 |

The trace links in the scenarios use `{{BASE_URL}}`; the integration test substitutes a local
Langfuse-compatible stub so verification runs for real without network access.
