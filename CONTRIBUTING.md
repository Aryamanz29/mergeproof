# Contributing

```sh
make setup        # uv sync, example plugin, pre-commit hooks
make lint typecheck test
make integration  # slower: builds nothing, but spawns the CLI and the MCP server
make check        # this repository's own gate, against your working tree
```

Pull requests here are gated by `mergeproof.yaml` at the root. Run `mergeproof explain` before
pushing to see what your change must prove; the CI comment will say the same thing.

Guidelines:

- One idea per module. If a file needs a section divider, it wants to be two files.
- A check does one thing, has a pydantic `Params` model, and explains itself in one sentence.
- Nothing vendor-specific in the core. Vendor support is a verifier or check plugin (see
  `examples/plugins/`).
- Tests that exercise a real boundary (a subprocess, an HTTP call, a git repository) belong in
  `tests/integration` and are marked `integration`.
- Add a line to `CHANGELOG.md` under Unreleased for anything a user would notice.
