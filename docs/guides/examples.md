# Examples

The repository ships three example projects and two plugins. Each example has a policy, a README
explaining the reasoning, and `scenarios/`: pull request contexts, as JSON, with the verdict
expected from them. The integration suite runs every scenario through the installed CLI, so the
examples cannot rot.

| Example | Shows |
|---|---|
| [`python-library`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/python-library) | tests for touched modules, a changelog entry, green CI |
| [`mcp-server`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/mcp-server) | unit and integration tests for tools, before/after traces from an open-source tracer, human sign-off, an LLM reviewer's verdict |
| [`web-service`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/web-service) | migrations need rollback notes, UI changes need screenshots, sensitive paths need a label |
| [`plugins/mergeproof-langfuse`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-langfuse) | a verifier that looks trace links up in Langfuse |
| [`plugins/mergeproof-braintrust`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-braintrust) | the same for Braintrust, through BTQL |

Run one:

```sh
mergeproof check --policy examples/python-library/mergeproof.yaml \
                 --context examples/python-library/scenarios/missing-tests.json
```

Scenario files are what `mergeproof context` prints. Capturing one from a real PR and committing
it next to the policy is the cheapest regression test a policy can have.
