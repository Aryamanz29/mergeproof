# mergeproof-langfuse

Verifies before/after trace links against a [Langfuse](https://langfuse.com) instance, so a
link pasted into a PR has to point at a trace that exists.

```sh
pip install mergeproof-langfuse
export LANGFUSE_PUBLIC_KEY=pk-... LANGFUSE_SECRET_KEY=sk-...
```

```yaml
- check: evidence.links
  with:
    key: traces
    pattern: "^(?P<host>https?://[^/]+)/project/(?P<project>[^/]+)/traces/(?P<trace_id>[\\w-]+)"
    verify: langfuse

# or, with the defaults above baked in:
- check: langfuse.traces
```

`verify_options` are passed to the verifier: `host` (when the API is not on the link's host),
`public_key_env`, `secret_key_env`, `timeout`.

## Writing a verifier for another backend

A verifier is a class with a constructor taking keyword options and a `verify(url, match)`
method returning a bool; `match` is the policy pattern's match object, so named groups such as
`trace_id` are available. Register it:

```toml
[project.entry-points."mergeproof.verifiers"]
jaeger = "mergeproof_jaeger:JaegerVerifier"
```

For Jaeger the lookup is `GET {host}/api/traces/{trace_id}`; for Arize Phoenix a GraphQL query
by trace id. Everything else in this package carries over unchanged.
