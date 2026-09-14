# Policy schema

`mergeproof.yaml` has a JSON schema, generated from the same models that validate it, so the two
cannot disagree:

```
https://aryamanz29.github.io/mergeproof/schema/mergeproof-v1.json
```

## Editor support

Put this on the first line of the policy and editors with a YAML language server (VS Code with
the YAML extension, JetBrains, Neovim with yamlls) complete keys, show descriptions and flag
mistakes as you type. `mergeproof init` writes it for you.

```yaml
# yaml-language-server: $schema=https://aryamanz29.github.io/mergeproof/schema/mergeproof-v1.json
```

`mergeproof schema` prints the current schema, for pinning a copy or feeding another tool. The
schema describes the *shape*; what a check accepts under `with:` is validated by the check itself
(`mergeproof validate`, `mergeproof checks`), because plugins add checks the schema cannot know.

## Versioning

`version: 1` at the top of the policy is a contract, not decoration. This mergeproof reads
version 1 and refuses anything else with a message saying so. The rules:

- Within a version, keys are only added. A policy that validated yesterday validates tomorrow;
  new keys have defaults that keep old behaviour.
- A key is removed or changes meaning only in a new policy version, released with a major
  version of mergeproof, and the previous version keeps being read for at least one major.
- The upgrade path for a new version ships with it: a `mergeproof migrate` command that rewrites
  the file and says what it changed, and a section here listing every change.

The version applies to the resolved policy: a base pulled in through `extends` must be the same
version as the file that extends it.
