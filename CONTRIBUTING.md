# Contributing

```sh
make setup        # uv sync, example plugin, pre-commit hooks
make lint typecheck test
make integration  # slower: spawns the CLI against the examples and the plugin
make check        # this repository's own gate, against your working tree
make docs-serve   # the documentation site, live-reloading at http://127.0.0.1:8000
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
- `CHANGELOG.md` is written by release-please from commit messages; do not edit it by hand.
- Documentation lives in `docs/` and is built with MkDocs; `make docs` fails on a broken link.

## Commits and releases

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org): `feat:`,
`fix:`, `docs:`, `ci:`, `test:`, `chore:`; a `!` or a `BREAKING CHANGE:` footer marks a breaking
change. The `commit-msg` hook installed by `make setup` checks the format. This is what drives
the release process:

1. Every push to `main` runs [release-please](https://github.com/googleapis/release-please), which
   opens or updates a single pull request titled `chore(main): release X.Y.Z`. The PR bumps the
   version in `pyproject.toml` and `src/mergeproof/__init__.py` and writes the `CHANGELOG.md`
   entry from the commits since the last release. `feat` bumps the minor version, `fix` the
   patch, a breaking change the major (minor while still 0.x). Squash-merge with the PR title as
   the commit subject; that title is the changelog line.
2. Review the generated changelog like any other PR; edit it in the PR if a line reads badly.
   With a `RELEASE_PLEASE_TOKEN` repository secret (a fine-grained personal access token with
   contents and pull requests read and write) the PR is opened as a person and CI starts on it;
   without it, close and reopen the PR once and the checks run.
3. Merging that PR creates the `vX.Y.Z` tag and the GitHub Release.
4. release-please then dispatches `release.yml` (wheel and sdist to PyPI through trusted publishing, attached to
   the GitHub Release) and `image.yml` (`ghcr.io/aryamanz29/mergeproof:X.Y.Z`, `:X.Y`, `:X`,
   `:latest`).

Nothing is versioned by hand. `v0.2.0` was the one manual bootstrap tag before this process
existed.
