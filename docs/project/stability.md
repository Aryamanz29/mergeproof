# Stability

What you can build on, and how it changes.

## The public API

Everything importable from the top-level `mergeproof` package is public:

| for | names |
|---|---|
| writing a check | `Check`, `Outcome`, `Status`, `Annotation`, and the outcome helpers `ok`, `fail`, `warn`, `pending`, `skip`, `error` |
| writing a verifier | `Verifier`, `Verification` |
| writing an evaluation check | `EvalScore`, `EvalRun`, `MissingCredentials` |
| what a check sees | `Context`, `ChangedFile`, `Comment`, `CheckRun` |
| what a check produces | `Report`, `RuleResult`, `RequirementResult` |
| the policy | `Policy`, `Rule`, `Requirement`, `When`, `Severity`, `PolicyError` |
| | `__version__` |

Plus the entry-point groups `mergeproof.checks` and `mergeproof.verifiers`, the `Params` inner
class convention, and the `run(ctx, params, files)`, `explain(params)`, `evidence_template(params)`
and `verify(url, match)` signatures.

Also public: the policy file format ([schema](../reference/schema.md)), the command line and its
exit codes, the action's inputs and outputs, the JSON report and receipt documents, and the
evidence block format.

Everything else under `mergeproof.*` (`providers`, `render`, `engine`, `replay`, `doctor`,
individual check modules) is internal. Import it if you must, and expect it to change in minors.

## How it changes

- From 1.0, semantic versioning: a public name or a documented behaviour changes incompatibly
  only in a major release.
- Before removing or changing something public, it is deprecated for at least one minor: it
  keeps working, emits a warning that names the replacement, and the changelog says so.
- Additions (a new field on `Outcome`, a new parameter with a default, a new command) land in
  minors and never break a plugin that ignores them.
- A test in this repository, `tests/unit/test_public_api.py`, pins the public surface and loads
  every example policy and both example plugins against it. Changing that list is a review
  conversation, not a side effect.

## Before 1.0

Until 1.0 the same rules are followed in spirit: breaking changes are announced in the changelog
with a migration line, and the floating `@v0` tag of the action only moved within 0.x.
