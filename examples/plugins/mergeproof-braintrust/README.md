# mergeproof-braintrust

Verifies before/after trace links against [Braintrust](https://www.braintrust.dev), so a link
pasted into a PR has to point at a log row that exists.

```sh
pip install mergeproof-braintrust      # or, in the action: plugins: mergeproof-braintrust
export BRAINTRUST_API_KEY=...          # a key with read access to the project
```

```yaml
- check: braintrust.traces             # evidence.links with Braintrust defaults
  with: { min_pairs: 1 }

# or spelled out:
- check: evidence.links
  with:
    key: traces
    pattern: "^https://www\\.braintrust\\.dev/app/(?P<org>[^/]+)/p/(?P<project>[^/?]+)/logs\\?(?:.*&)?r=(?P<trace_id>[0-9a-fA-F-]+)"
    verify: braintrust
    verify_options: { project: mcp-internal }   # pin the project instead of trusting the link
```

The lookup is `SELECT id FROM project_logs('<project>') WHERE id = '<id>' OR root_span_id = '<id>'`
over `POST /btql`. Only the project name and the id leave your CI. `verify_options`: `api_key_env`,
`api_url`, `project`, `timeout`.
