# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- PR comment redesigned: logo, status badge and links in the header, one plain sentence, one table with a Status column in words, numbered next steps only when something is missing, and no comment at all when no rule applies.
- `ci.job_passed` considers only the newest check run per name, so runs cancelled by a newer push no longer count as failures.
- The PR comment leads with a headline count, caps details, and carries the evaluation time.
- `mergeproof checks` marks checks that only produce results in GitHub mode.

### Added
- `-f junit` and `-f rdjson` renderings, written by the action, so test-result reporters and reviewdog can present the gate.
- Container image `ghcr.io/aryamanz29/mergeproof` with the CLI and MCP server; `:edge` on every push to main, version tags and `:latest` on releases.
- Reporting through the commit status (`--status`) and a Check Run with file annotations (`--check-run`); the action enables both by default.
- Container image `ghcr.io/aryamanz29/mergeproof` with the CLI and MCP server; published on every release tag.
- `mergeproof[otel]`: the MCP server exports OpenTelemetry spans over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (Langfuse, Jaeger, Phoenix, any collector).

## [0.2.0] - 2026-09-12

### Added
- Plumbing commands `context`, `report`, `comment` and `template`; contexts and reports are JSON and pipe between them.
- `mergeproof mcp`: an MCP server (stdio) exposing explain, check, evidence_block, validate_policy, list_checks and agent_instructions.
- `evidence.links`: vendor-neutral before/after link pairs with pluggable verifiers (`mergeproof.verifiers` entry-point group); `http` verifier built in.
- `files.changed` check.
- Example projects with scenario fixtures that the integration suite executes, and a `mergeproof-langfuse` verifier plugin.
- Fixed exit codes: 0 pass or warn, 1 fail, 2 pending, 3 usage or policy error.

### Removed
- Braintrust-specific trace check (`evidence.traces`). Use `evidence.links` with a verifier plugin.

## [0.1.0] - 2026-09-12

### Added
- First cut: policy file, built-in checks, `check` / `explain` / `agent-prompt`, composite GitHub Action.
