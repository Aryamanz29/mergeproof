# AGENTS.md

Instructions for coding agents working in this repository. The section below is generated
from `mergeproof.yaml` with `mergeproof agent-prompt`; edit the policy, not this file.

## Working here

- `make setup` once, then `make lint typecheck test` before every push; `make integration` when you touch the CLI, examples, plugin or MCP server.
- `mergeproof explain` shows what your change must prove. `mergeproof template` prints the evidence block still missing.
- The MCP server is configured in `.mcp.json`; the `explain` and `check` tools give the same answers.
- Style: small modules that do one thing, no decorative comment banners, pydantic models for parameters, one-sentence `explain()` per check, nothing vendor-specific in the core.
- Do not add attribution trailers to commits.

## Evidence requirements (enforced in CI by mergeproof)

Pull requests are gated on evidence, not on claims. Before opening or updating a PR run `mergeproof explain` and satisfy every listed requirement. Evidence goes in a fenced ```evidence block in the PR description.

### `source-needs-tests`: A change to a module ships with a change to its tests.

**When:** files matching `src/mergeproof/**/*.py`; except `src/mergeproof/__init__.py`, `src/mergeproof/__main__.py`, `src/mergeproof/mcp_server.py`. **Severity:** block.

- **unit tests touched**: Each changed source file needs a changed test file: `src/mergeproof/checks/{name}.py` needs `tests/unit/test_checks.py`; `src/mergeproof/providers/{name}.py` needs `tests/unit/test_providers.py`; `src/mergeproof/verifiers/{name}.py` needs `tests/unit/test_verifiers.py`; `src/mergeproof/render/{name}.py` needs `tests/unit/test_render.py`; `src/mergeproof/{name}.py` needs `tests/unit/test_{name}*.py`.
- **unit tests green on every Python**: CI check run matching `^unit \(3\.1[123]\)$` is green on the head commit.
- **integration green**: CI check run matching `^integration$` is green on the head commit.

### `mcp-server-has-integration-test`: The MCP server is only tested end to end, so a change there touches that test.

**When:** files matching `src/mergeproof/mcp_server.py`. **Severity:** block.

- **tests.changed**: At least one changed test file matching `tests/integration/test_mcp.py`.

### `examples-stay-runnable`: A changed example policy keeps or updates its scenarios.

**When:** files matching `examples/*/mergeproof.yaml`. **Severity:** block.

- **scenarios touched**: Change at least one of `examples/*/scenarios/*.json`.

### `changelog`: User-visible changes are recorded.

**When:** files matching `src/**`, `action.yml`. **Severity:** warn.

- **files.changed**: Change `changelog.md`.
  - Add a line under Unreleased in CHANGELOG.md.

### Rules for agents

- Never fabricate evidence. If you cannot produce a required artifact, say so in the PR and leave the field out; the gate stays pending until a human decides.
- Requirements of type `review.human_verified` can only be satisfied by a human other than the author. Do not post the verification phrase.
- Keep the evidence block plain YAML. Do not wrap links in extra Markdown.
