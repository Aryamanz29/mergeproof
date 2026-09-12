# Runs the CLI and the MCP server without a local Python install.
#
#   docker run --rm -v "$PWD":/repo ghcr.io/aryamanz29/mergeproof check --local
#   docker run -i --rm -v "$PWD":/repo ghcr.io/aryamanz29/mergeproof mcp
#
# The repository is expected at /repo (the working directory). git is included because the
# local provider reads the diff from it.

FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN pip install --no-cache-dir --quiet build && python -m build --wheel --outdir /wheels

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/Aryamanz29/mergeproof" \
      org.opencontainers.image.description="Evidence gates for pull requests: CLI and MCP server" \
      org.opencontainers.image.licenses="MIT"
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 mergeproof
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --quiet "$(ls /wheels/*.whl)[mcp,otel]" && rm -rf /wheels
# Mounted repositories are usually owned by a different uid than the container user.
ENV GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=* \
    PYTHONUNBUFFERED=1 MERGEPROOF_POLICY=mergeproof.yaml
USER mergeproof
WORKDIR /repo
ENTRYPOINT ["mergeproof"]
CMD ["--help"]
