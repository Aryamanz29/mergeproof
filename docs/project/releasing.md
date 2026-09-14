# Releasing

Nothing is versioned by hand.

1. Commits on `main` follow Conventional Commits. `feat` bumps the minor version (while 0.x),
   `fix` the patch, a breaking change the next minor while 0.x and the major after 1.0.
2. On every push to `main`, release-please opens or updates one pull request,
   `chore(main): release X.Y.Z`, with the version bump and the changelog entry.
3. Merging that PR creates the tag and the GitHub Release, then dispatches the publish workflows.
4. `release.yml` builds the wheel and sdist, publishes to PyPI through trusted publishing, attaches
   both to the Release, and moves the floating `vX` tag. `image.yml` pushes
   `ghcr.io/aryamanz29/mergeproof:X.Y.Z`, `:X.Y`, `:X` and `:latest`.

Pull requests opened by the workflow token do not start CI on their own; the release-please job
dispatches CI onto the release PR, or configure a `RELEASE_PLEASE_TOKEN` secret.

## Cutting 1.0

While the version is 0.x, `bump-minor-pre-major` makes a breaking change bump the minor, so 1.0
does not happen by accident. To cut it, merge a commit whose footer says `Release-As: 1.0.0`;
release-please then opens the 1.0.0 release PR. After that, remove `bump-minor-pre-major` from
`release-please-config.json` so the next `feat!` bumps the major, as [Stability](stability.md)
promises.
