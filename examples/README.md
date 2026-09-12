# Examples

Each directory holds a policy, a README explaining the reasoning, and a `scenarios/` folder with
pull-request contexts (the JSON `mergeproof context` prints) together with the verdict expected
from them. The integration suite runs every scenario through the installed CLI, so the examples
cannot silently rot.

| Example | Shows |
|---|---|
| [`python-library/`](python-library/) | tests for touched modules, a changelog entry, green CI |
| [`mcp-server/`](mcp-server/) | unit + integration tests for tools, before/after traces from an open-source tracer, human sign-off, an LLM reviewer's verdict |
| [`web-service/`](web-service/) | migrations need rollback notes, UI changes need screenshots, sensitive paths need a label |
| [`plugins/mergeproof-langfuse/`](plugins/mergeproof-langfuse/) | a verifier plugin that looks trace links up in Langfuse |

Run one yourself:

```sh
mergeproof check --policy examples/python-library/mergeproof.yaml \
                 --context examples/python-library/scenarios/missing-tests.json
```
