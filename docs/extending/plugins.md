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
messages that become job annotations and review comments). `explain` is what agents read; keep it one sentence.

```toml
[project.entry-points."mergeproof.checks"]
"image.smoke_tested" = "mypkg.checks:ImageSmokeTested"
```

## When a shell check should become a plugin

`shell` is for trying an idea in an afternoon. It stops being the right tool when any of these is
true:

- **The command encodes a rule someone else could reuse.** Two repositories running the same
  script have a plugin waiting to be written.
- **An agent needs to satisfy it.** `shell` explains itself as "`the command` exits 0"; a check
  explains what to change and where, in one sentence the agent can act on.
- **It reads the pull request.** The command runs in the checkout of the *base* branch and only
  sees the changed paths through `MERGEPROOF_FILES`; a check gets the whole `Context` (files with
  status, description, evidence block, comments, reviews, check runs, repository tree).
- **The result should carry evidence.** A check returns `details`, `data` and annotations that
  reach the comment, the review comments and the receipt; a script returns an exit code.

`mergeproof validate` prints a note for every `shell` requirement and `mergeproof checks --usage
-p mergeproof.yaml` lists their commands, so the escape hatch stays visible.

The plugin is small. A check class:

```python
# mypkg/checks.py
from pydantic import BaseModel, ConfigDict, Field

from mergeproof import Check, Context, Outcome
from mergeproof.checks.base import fail, ok


class BaselineUpdated(Check):
    id = "tools.baseline"
    description = "A tool schema change comes with a regenerated baseline file."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        baseline: str = Field(default="tests/baselines/tool_surface.json")

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        if any(f.path == params.baseline for f in ctx.files):
            return ok(f"{params.baseline} updated")
        return fail(f"{params.baseline} unchanged", fix=self.explain(params))

    def explain(self, params: Params) -> str:
        return f"Regenerate `{params.baseline}` when a tool's schema changes and commit it."
```

An entry point, so the policy can name it:

```toml
[project.entry-points."mergeproof.checks"]
"tools.baseline" = "mypkg.checks:BaselineUpdated"
```

And a test that drives it with a `Context`, the way `tests/unit/test_checks.py` does for the
built-ins:

```python
from mergeproof.context import ChangedFile, Context
from mypkg.checks import BaselineUpdated


def test_baseline_must_change():
    check = BaselineUpdated()
    params = check.parse_params({})
    ctx = Context(files=[ChangedFile(path="tools/search.py")])
    assert check.run(ctx, params, ["tools/search.py"]).status == "fail"
```

Install the package next to mergeproof (the action's `plugins` input) and the policy says
`check: tools.baseline`. The two plugins under `examples/plugins/` are complete examples with
packaging and tests.

### An evaluation check

If your evaluation backend is not Braintrust or Langfuse, subclass `EvalScore` instead of `Check`:
declare `id` and `source`, extend `Params` with what your API needs, and implement
`fetch_run(ref, match, params) -> EvalRun` (id, name, timestamp, example count, `scores` by name).
Reading the reference from the evidence block, comparing with the thresholds, the optional
baseline, the explanation and the evidence template are all inherited. Raise `MissingCredentials`
when you cannot authenticate and the requirement stays pending with your message; raise
`ValueError` for a reference you cannot resolve and it fails with the message. The two plugins
under `examples/plugins/` are the worked examples.

## A verifier

A verifier resolves a link from `evidence.links` to an answer with provenance. It is a class
taking keyword options and exposing `verify(url, match)`, where `match` is the policy pattern's
match object, so named groups such as `trace_id` are available. Return a bool for yes or no, or a
`Verification` to say *what* was found: the object's id, when it was recorded, how big it is, and
any facts worth keeping. The comment shows that line next to the link and the receipt stores it,
so a reviewer can tell a real trace from an empty one without opening it.

```python
import httpx

from mergeproof.verifiers import Verification


class JaegerVerifier:
    def __init__(self, host: str | None = None, timeout: float = 15.0) -> None:
        self.host = host
        self._client = httpx.Client(timeout=timeout)

    def verify(self, url: str, match) -> Verification:
        host = self.host or match.group("host")
        response = self._client.get(f"{host}/api/traces/{match.group('trace_id')}")
        if response.status_code != 200:
            return Verification(found=False, source="jaeger")
        trace = response.json()["data"][0]
        return Verification(
            found=True,
            source="jaeger",
            id=trace["traceID"],
            size=f"{len(trace['spans'])} spans",
            facts={"service": trace["processes"]["p1"]["serviceName"]},
        )
```

`Verification.line()` renders as `jaeger · frontend · 14 spans`; every field except `found` is
optional, and a plain `return True` still works.

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

The complete worked example is [`examples/plugins/mergeproof-langfuse`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-langfuse):
a verifier for Langfuse and a `langfuse.traces` check that is `evidence.links` with Langfuse
defaults, in about forty lines with tests. [`mergeproof-braintrust`](https://github.com/Aryamanz29/mergeproof/tree/main/examples/plugins/mergeproof-braintrust)
is the same shape for Braintrust, looking ids up through BTQL.
