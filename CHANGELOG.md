# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). From 0.2.0 on, entries are generated
by release-please from Conventional Commit messages.

## [1.0.2](https://github.com/Aryamanz29/mergeproof/compare/v1.0.1...v1.0.2) (2026-09-15)


### Fixed

* **report:** show every before/after pair, one line each ([1dacff4](https://github.com/Aryamanz29/mergeproof/commit/1dacff4b8508c68bcb1519ef36d201bc827d8516))
* **report:** show every before/after pair, one line each ([522b6cf](https://github.com/Aryamanz29/mergeproof/commit/522b6cf5a9ed1e9b7c6853b74ab09e9366679ac9))

## [1.0.1](https://github.com/Aryamanz29/mergeproof/compare/v1.0.0...v1.0.1) (2026-09-15)


### Fixed

* **report:** carry the evidence URL on verified lines ([90da300](https://github.com/Aryamanz29/mergeproof/commit/90da30021cc849968db52d0761cd6a690bf42775))
* **report:** carry the evidence URL on verified lines ([b7176fc](https://github.com/Aryamanz29/mergeproof/commit/b7176fcfbc355479383132bf50f2a688af9d5007))

## [1.0.0](https://github.com/Aryamanz29/mergeproof/compare/v0.6.0...v1.0.0) (2026-09-14)


### ⚠ BREAKING CHANGES

* remove the check-run option; the commit status is the signal

### Added

* **checks:** approving review can satisfy review.human_verified ([a660f60](https://github.com/Aryamanz29/mergeproof/commit/a660f60698e474dc4488cf45997ef59d9ee9d91a))
* **checks:** approving review can satisfy review.human_verified ([aac963a](https://github.com/Aryamanz29/mergeproof/commit/aac963a7764d955372cb7d7441fd6d0deee66dfa))
* **checks:** evaluation-run check for prompt and model changes ([551748a](https://github.com/Aryamanz29/mergeproof/commit/551748ad6f02e37a97b3d4ca4baf57e5189a1704))
* **checks:** evaluation-run check for prompt and model changes ([0e79bf1](https://github.com/Aryamanz29/mergeproof/commit/0e79bf1353721321dec987ab99351da97b7eda01)), closes [#50](https://github.com/Aryamanz29/mergeproof/issues/50)
* **checks:** evidence.artifacts with pair, single and set kinds ([16021b2](https://github.com/Aryamanz29/mergeproof/commit/16021b241cf38cfd56cc9f438161d0a1c839d629))
* **checks:** evidence.artifacts with pair, single and set kinds ([0c06980](https://github.com/Aryamanz29/mergeproof/commit/0c06980e35b39e1850293fb4e4c883d3fd6d8ce9)), closes [#47](https://github.com/Aryamanz29/mergeproof/issues/47)
* **cli:** doctor checks the policy, the workflow and the branch rules ([b92103d](https://github.com/Aryamanz29/mergeproof/commit/b92103d341290e2cf9631c82cabd7d5ba9e151f9))
* **cli:** doctor checks the policy, the workflow and the branch rules ([85acc8b](https://github.com/Aryamanz29/mergeproof/commit/85acc8bd251634dd1c0f81197cc21f9e488ccf96)), closes [#49](https://github.com/Aryamanz29/mergeproof/issues/49)
* **cli:** keep shell checks visible; document when one should become a plugin ([3c938c3](https://github.com/Aryamanz29/mergeproof/commit/3c938c36b02eb8091474b6696efe637b59f80350))
* **cli:** keep shell checks visible; document when one should become a plugin ([0038f66](https://github.com/Aryamanz29/mergeproof/commit/0038f66013b6bca7f2a99053b8531cfe262536f9)), closes [#53](https://github.com/Aryamanz29/mergeproof/issues/53)
* **cli:** replay a policy against merged pull requests ([c778417](https://github.com/Aryamanz29/mergeproof/commit/c7784179ab3ae1f2959619100fb2d05922a20cd1))
* **cli:** replay a policy against merged pull requests ([bdd6614](https://github.com/Aryamanz29/mergeproof/commit/bdd66148e601889af01e2f9b943f9249d884dfc4)), closes [#44](https://github.com/Aryamanz29/mergeproof/issues/44)
* **policy:** extends pulls rules from pinned base policies ([9b8d138](https://github.com/Aryamanz29/mergeproof/commit/9b8d1387d188b3293764a7cce21f2016d6b4a549))
* **policy:** extends pulls rules from pinned base policies ([94aa654](https://github.com/Aryamanz29/mergeproof/commit/94aa6544cf24c699b1b85bdbb628513661e243e2)), closes [#45](https://github.com/Aryamanz29/mergeproof/issues/45)
* **receipt:** store the final report on a branch when the pull request merges ([312172c](https://github.com/Aryamanz29/mergeproof/commit/312172c6f985d0beaf0da5249dc91ef18796f2c8))
* **receipt:** store the final report on a branch when the pull request merges ([ad9c3b7](https://github.com/Aryamanz29/mergeproof/commit/ad9c3b70c750f6b5d0c33d0792b75aa59f453d26)), closes [#43](https://github.com/Aryamanz29/mergeproof/issues/43)
* remove the check-run option; the commit status is the signal ([f71b8f8](https://github.com/Aryamanz29/mergeproof/commit/f71b8f819b908f529d06c7d12af82e8197d147b4)), closes [#48](https://github.com/Aryamanz29/mergeproof/issues/48)
* **report:** review comments on the files concerned; one truth for counts ([adc32c6](https://github.com/Aryamanz29/mergeproof/commit/adc32c66e85b04a12451e2d6af0e1e5d2a46673c))
* **report:** review comments on the files concerned; one truth for counts ([bd7a41b](https://github.com/Aryamanz29/mergeproof/commit/bd7a41b71e1c01525436adf8fef5026f2880bf3c))
* **report:** scorecard comment ([69dd3b4](https://github.com/Aryamanz29/mergeproof/commit/69dd3b4536ffaa1d86b13fab9ca96429ce9fd53e))
* the 1.0 contract: policy schema, version check, frozen public API ([e6d685e](https://github.com/Aryamanz29/mergeproof/commit/e6d685e8f10418336673d989a9f553e1185fe3a7))
* the 1.0 contract: policy schema, version check, frozen public API ([c8af670](https://github.com/Aryamanz29/mergeproof/commit/c8af6705f22c4fd7a075cf3adc2f3fa593cd762f)), closes [#52](https://github.com/Aryamanz29/mergeproof/issues/52)
* **verifiers:** results carry provenance ([4fc9f28](https://github.com/Aryamanz29/mergeproof/commit/4fc9f281a8ee8a81f99f333904eaa4a21a289b1d))
* **verifiers:** results carry provenance ([a3a1ec0](https://github.com/Aryamanz29/mergeproof/commit/a3a1ec08f81fda9581e88674cffd0a6747ff96ff)), closes [#46](https://github.com/Aryamanz29/mergeproof/issues/46)


### Fixed

* **cli:** publish review comments when asked ([ded5b26](https://github.com/Aryamanz29/mergeproof/commit/ded5b26921a519dcb18a446247855c7650af63ec))
* **report:** publish review comments when asked; integration assertion follows the new header ([453615a](https://github.com/Aryamanz29/mergeproof/commit/453615a57455b59100310b0aed452fa6887a5dc1))


### Documentation

* checkout ref in block style; the flow form was not valid YAML ([3160ccd](https://github.com/Aryamanz29/mergeproof/commit/3160ccd8cf88951fc206e44a1ed25d9fc31b25d4))
* checkout ref in block style; the flow form was not valid YAML ([bbbd5e5](https://github.com/Aryamanz29/mergeproof/commit/bbbd5e5dbc4bc64ed12b758f8be857192b79abbb))
* documentation site with MkDocs Material, README revamp ([ae7989c](https://github.com/Aryamanz29/mergeproof/commit/ae7989c7f7136f3622ff53b614f023d39b6292a3))
* documentation site with MkDocs Material, README revamp ([b736eff](https://github.com/Aryamanz29/mergeproof/commit/b736eff3e8c921c710e8e5c9bb7b5c1b8fe55bbe))
* documentation site with MkDocs Material, README revamp ([0cf0642](https://github.com/Aryamanz29/mergeproof/commit/0cf06421efc09a56ab42494121553bdb07291612))
* how-it-works diagram drawn with D2 ([509865c](https://github.com/Aryamanz29/mergeproof/commit/509865c1f3cd8e7c0299b801aea5fa4c3d501996))
* how-it-works diagram drawn with D2, used by the README and the docs site ([71d9ad5](https://github.com/Aryamanz29/mergeproof/commit/71d9ad52878474e4df35e620bdb9fb23f5dea81f))
* **readme:** absolute image and link URLs so PyPI renders it ([6156555](https://github.com/Aryamanz29/mergeproof/commit/61565559b5cfdb4505f3c2d0a7824f8405b9d296))
* **readme:** real screenshots, a flow diagram and a script that regenerates them ([5bd6be8](https://github.com/Aryamanz29/mergeproof/commit/5bd6be85f3a32a7c3fd9753c5032b70eee7e01cc))
* **readme:** real screenshots, a flow diagram and a script that regenerates them ([2deb265](https://github.com/Aryamanz29/mergeproof/commit/2deb2654f061377aa9227b219357dc7b8708efc4))
* **readme:** same wordmark as the docs site ([24aa865](https://github.com/Aryamanz29/mergeproof/commit/24aa8655fc0e8f70681e2780f179be48e24b367e))
* **readme:** size screenshots to their content; plain-text mermaid labels ([a5dbec3](https://github.com/Aryamanz29/mergeproof/commit/a5dbec39b46e6bb7643ef2cc0b917c61531e2a31))
* render octicon shortcodes on the landing page ([321989a](https://github.com/Aryamanz29/mergeproof/commit/321989a6a2fa465c08f8fba8e0528e8c2fce7e76))


### Chores

* **release:** cut 1.0.0 ([5cbec3b](https://github.com/Aryamanz29/mergeproof/commit/5cbec3b537b10fb1f9a76013f323b7a0e2354a9d))

## [0.6.0](https://github.com/Aryamanz29/mergeproof/compare/v0.5.0...v0.6.0) (2026-09-12)


### Added

* **action:** the commit status is the required signal; annotations come from the job ([c2ceb4a](https://github.com/Aryamanz29/mergeproof/commit/c2ceb4a26d2153cf3bc52277095cb34db4e8d095))
* **action:** the commit status is the required signal; annotations come from the job ([b0988f5](https://github.com/Aryamanz29/mergeproof/commit/b0988f5b9b45c0029bbd4f979e02678590e20a4e))


### Fixed

* **cli:** workflow commands only alongside text output ([4218fd7](https://github.com/Aryamanz29/mergeproof/commit/4218fd7a027e96768a5cc44b738fdea7ed84710f))

## [0.5.0](https://github.com/Aryamanz29/mergeproof/compare/v0.4.0...v0.5.0) (2026-09-12)


### Added

* **checks:** tests.changed existing_only ([2f35869](https://github.com/Aryamanz29/mergeproof/commit/2f35869a4e18d155af1cbea2688bacdae578e275))
* **plugins:** Braintrust verifier plugin ([7080d6c](https://github.com/Aryamanz29/mergeproof/commit/7080d6c67b93187d3fbecfb5a9176eb7938684b1))
* **plugins:** mergeproof-braintrust verifier and braintrust.traces check ([13bcfff](https://github.com/Aryamanz29/mergeproof/commit/13bcfff0c042b79a94cc339b58313ebf264c52cb))

## [0.4.0](https://github.com/Aryamanz29/mergeproof/compare/v0.3.0...v0.4.0) (2026-09-12)


### ⚠ BREAKING CHANGES

* the `mergeproof mcp` command and the `mcp` and `otel` extras are removed.

### Added

* **action:** one mergeproof row in the checks list ([5d41125](https://github.com/Aryamanz29/mergeproof/commit/5d41125abcba3cbb190e272862c89f7e7a81e2bd))
* **action:** one mergeproof row; manual dispatch for the publish workflows ([d9ec0f6](https://github.com/Aryamanz29/mergeproof/commit/d9ec0f64105ce280df2e8f6282c18237d846eaa7))
* drop the MCP server and OpenTelemetry export ([97ac367](https://github.com/Aryamanz29/mergeproof/commit/97ac367f1d5ae71fc5d3b0308cf19098f885bdc5))

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
