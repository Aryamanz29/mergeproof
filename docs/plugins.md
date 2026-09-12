# Plugins

Anything vendor-specific lives outside the core, as a Python package that registers entry points.
Install it next to `mergeproof` (in CI: the action's `plugins` input) and its checks and verifiers
become available to any policy.

## A check

```python
from pydantic import BaseModel
from mergeproof import Check, Context, Outcome, Status


class ImageSmokeTested(Check):
    id = "image.smoke_tested"
    description = "The image named in the evidence block was exercised against the environment."

    class Params(BaseModel):
        registry: str

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        tag = ctx.evidence().get("image")
        if not tag or not tag.startswith(params.registry):
            return Outcome(
                status=Status.FAIL,
                summary="no image under the expected registry",
                fix="Build the branch image and record its tag under `image`.",
            )
        # query your deployment API here
        return Outcome(status=Status.PASS, summary=f"{tag} smoke-tested")

    def explain(self, params: Params) -> str:
        return f"An image under `{params.registry}` recorded as `image` and smoke-tested."

    def evidence_template(self, params: Params) -> dict:
        return {"image": f"{params.registry}/<name>:pr-<n>-<sha7>"}
```

`Context` gives you the changed files, title, body, labels, comments, check runs and the parsed
evidence block. `files` are the changed paths that made the rule apply. Return `Outcome` with a
status, a one-line summary, optional `details`, a `fix` sentence and `annotations` (file-level
messages that become Check Run annotations). `explain` is what agents read; keep it one sentence.

```toml
[project.entry-points."mergeproof.checks"]
"image.smoke_tested" = "mypkg.checks:ImageSmokeTested"
```

## A verifier

A verifier resolves a link from `evidence.links` to a yes or no. It is a class taking keyword
options and exposing `verify(url, match)`, where `match` is the policy pattern's match object, so
named groups such as `trace_id` are available.

```python
import httpx


class JaegerVerifier:
    def __init__(self, host: str | None = None, timeout: float = 15.0) -> None:
        self.host = host
        self._client = httpx.Client(timeout=timeout)

    def verify(self, url: str, match) -> bool:
        host = self.host or match.group("host")
        response = self._client.get(f"{host}/api/traces/{match.group('trace_id')}")
        return response.status_code == 200
```

```toml
[project.entry-points."mergeproof.verifiers"]
jaeger = "mypkg.verifiers:JaegerVerifier"
```

```yaml
- check: evidence.links
  with:
    pattern: "^(?P<host>https?://[^/]+)/trace/(?P<trace_id>[\\w-]+)"
    verify: jaeger
```

The complete worked example is [`examples/plugins/mergeproof-langfuse`](../examples/plugins/mergeproof-langfuse):
a verifier for Langfuse and a `langfuse.traces` check that is `evidence.links` with Langfuse
defaults, in about forty lines with tests.
