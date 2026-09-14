# Install

=== "pip / uv"

    ```sh
    pip install mergeproof
    # or, as a tool on your PATH
    uv tool install mergeproof
    ```

=== "Run without installing"

    ```sh
    uvx mergeproof explain
    docker run --rm -v "$PWD":/repo ghcr.io/aryamanz29/mergeproof check --local
    ```

    The image expects the repository mounted at `/repo`. Tags follow releases: `X.Y.Z`, `X.Y`,
    `X`, `latest`; `edge` tracks `main`.

=== "GitHub Actions"

    ```yaml
    - uses: Aryamanz29/mergeproof@v0
    ```

    `@v0` follows the latest 0.x release; pin `@vX.Y.Z` or a commit SHA for an exact one.

Requires Python 3.11 or newer and `git` on the PATH for local mode.

## Plugins

Vendor-specific verifiers and checks are separate packages. In CI, pass them to the action's
`plugins` input; locally, `pip install` them next to mergeproof.

```yaml
- uses: Aryamanz29/mergeproof@v0
  with:
    plugins: "git+https://github.com/Aryamanz29/mergeproof@v0#subdirectory=examples/plugins/mergeproof-braintrust"
```

See [Plugins](../extending/plugins.md).
