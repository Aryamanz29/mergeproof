# shared-policy

One organisation policy, many repositories. `policies/python-service.yaml` is the base an
organisation keeps in a policies repository; `mergeproof.yaml` is what one service checks in:

```yaml
extends: github:acme/policies/python-service.yaml@v1
```

The example uses `path:` so it runs offline; the semantics are the same. The local file

- **replaces** `source-needs-tests` by id, because this service keeps tests next to the code;
- **disables** `changelog` with `enabled: false`;
- **adds** `payment-code-is-reviewed-by-owners`;
- keeps `migrations-need-rollback` from the base untouched.

`mergeproof validate --policy examples/shared-policy/mergeproof.yaml` lists which file each rule
came from. Remote bases must be pinned to a tag or a commit sha; a branch is refused so that a pull
request cannot change its own gate.

## Scenarios

| file | expected |
|---|---|
| `override-applies.json` | pass: the local test mapping is the one that counts, and no changelog nag |
| `base-rule-still-applies.json` | fail: a migration without a rollback note, a base rule this file never mentions |
| `added-rule-blocks.json` | fail: payments code without the owners' label |
