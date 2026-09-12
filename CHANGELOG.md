# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). From 0.2.0 on, entries are generated
by release-please from Conventional Commit messages.

## [0.3.0](https://github.com/Aryamanz29/mergeproof/compare/v0.2.0...v0.3.0) (2026-09-12)


### Added

* **report:** shield mark on check and status rows, and on the job name ([0fbb1d3](https://github.com/Aryamanz29/mergeproof/commit/0fbb1d330a6fc214f9614742ff063cf5cc749e3a))
* **report:** shield mark on the check, status and job rows ([b840382](https://github.com/Aryamanz29/mergeproof/commit/b8403828d52678be123e8ebf3c4eadb46ca303b5))


### Fixed

* **report:** keep the commit status description plain ([408cef7](https://github.com/Aryamanz29/mergeproof/commit/408cef7f7a8aa25bb7c93b61f5aee75c24d5c589))


### Documentation

* format the Python samples the way ruff wants ([a9cb946](https://github.com/Aryamanz29/mergeproof/commit/a9cb9469f72523251b0c1a995104d7797659c08d))
* short README with reference pages under docs/ ([7182fd5](https://github.com/Aryamanz29/mergeproof/commit/7182fd5a6530f65807a0704ebf979a29dfdd9729))
* short README, reference pages under docs/ ([5250153](https://github.com/Aryamanz29/mergeproof/commit/5250153db2eda535a0e89747d3353d52508fb4d4))

## [Unreleased]

## [0.2.0] - 2026-09-13

### Added
- Plumbing commands `context`, `report`, `comment` and `template`; contexts and reports are JSON and pipe between them.
- `mergeproof mcp`: an MCP server (stdio) exposing explain, check, evidence_block, validate_policy, list_checks and agent_instructions.
- `mergeproof[otel]`: the MCP server exports OpenTelemetry spans over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (Langfuse, Jaeger, Phoenix, any collector).
- `evidence.links`: vendor-neutral before/after link pairs with pluggable verifiers (`mergeproof.verifiers` entry-point group); `http` verifier built in.
- `files.changed` check.
- Reporting through the commit status (`--status`) and a Check Run with file annotations (`--check-run`); the action enables both by default.
- `-f junit` and `-f rdjson` renderings, written by the action, so test-result reporters and reviewdog can present the gate.
- Container image `ghcr.io/aryamanz29/mergeproof` with the CLI and MCP server: `:edge` on every push to main, `:X.Y.Z`, `:X.Y`, `:X` and `:latest` on release tags.
- Example projects with scenario fixtures that the integration suite executes, and a `mergeproof-langfuse` verifier plugin.
- Fixed exit codes: 0 pass or warn, 1 fail, 2 pending, 3 usage or policy error.

### Changed
- PR comment redesigned: logo, status badge and links in the header, one plain sentence, one table with a Status column in words, numbered next steps only when something is missing, and no comment at all when no rule applies.
- `ci.job_passed` considers only the newest check run per name, so runs cancelled by a newer push no longer count as failures.
- `mergeproof checks` marks checks that only produce results in GitHub mode.

### Removed
- Braintrust-specific trace check (`evidence.traces`). Use `evidence.links` with a verifier plugin.

## [0.1.0] - 2026-09-12

### Added
- First cut: policy file, built-in checks, `check` / `explain` / `agent-prompt`, composite GitHub Action.
